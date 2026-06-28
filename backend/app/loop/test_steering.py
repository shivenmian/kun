"""Tests for live steering — control file, approval gate, instruct, fork (§9).

Two layers:
  * PURE unit tests for the readers/resolvers in ``steering.py``.
  * HERMETIC integration tests that drive ``run_mission`` with the heuristic
    planner (no API key) and a FAKE runner (no training), in a temp runs/ dir,
    asserting that stop/pause/approve/reject actually steer the loop.

Run: cd backend && source <repo>/backend/.venv/bin/activate \
        && python app/loop/test_steering.py
"""
import json
import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from kun.log import kun_log  # noqa: E402

import app.loop.run_mission as RM  # noqa: E402
from app.loop import steering as ST  # noqa: E402
from app.loop.planner import NodeView, PlanContext, propose  # noqa: E402
from app.loop.schemas import Constraint  # noqa: E402


class _NoLLM:
    """Force the deterministic heuristic planner so integration tests are
    hermetic + fast even when an API key is present in the environment."""

    def __init__(self, *a, **k):
        pass

    def available(self):
        return False


# All integration runs below drive the heuristic path (no live LLM calls).
RM.LLMClient = _NoLLM


# --- pure: control file -------------------------------------------------------

def test_control_defaults_when_absent_or_malformed():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "control.json")
        assert ST.read_control(p) == {"run_state": "run", "approval_required": False}
        with open(p, "w") as f:
            f.write("{ not json")
        assert ST.read_control(p) == {"run_state": "run", "approval_required": False}
        # unknown run_state falls back to "run"; approval coerced to bool
        with open(p, "w") as f:
            json.dump({"run_state": "explode", "approval_required": 1}, f)
        assert ST.read_control(p) == {"run_state": "run", "approval_required": True}


def test_control_parses_valid_states():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "control.json")
        for st in ("run", "pause", "stop"):
            with open(p, "w") as f:
                json.dump({"run_state": st, "approval_required": False}, f)
            assert ST.read_control(p)["run_state"] == st


def test_exp_num():
    assert ST.exp_num("exp_007") == 7
    assert ST.exp_num("exp_000") == 0
    assert ST.exp_num(None) is None
    assert ST.exp_num("nope") is None


# --- pure: approval resolution ------------------------------------------------

def _ev(t, exp_id=None, payload=None):
    e = {"type": t, "payload": payload or {}}
    if exp_id:
        e["experiment_id"] = exp_id
    return e


def test_resolve_approval_all_cases():
    eid = "exp_000"
    assert ST.resolve_approval([], eid) is None  # unresolved
    assert ST.resolve_approval(
        [_ev("experiment_approved", eid, {"edited": False})], eid).kind == "approved"
    o = ST.resolve_approval(
        [_ev("experiment_approved", eid, {"edited": True, "changes": {"dropout": 0.3}})], eid)
    assert o.kind == "approved_edited" and o.changes == {"dropout": 0.3}
    o = ST.resolve_approval(
        [_ev("experiment_rejected", eid, {"replacement_changes": {"dropout": 0.2}})], eid)
    assert o.kind == "rejected_replacement" and o.changes == {"dropout": 0.2}
    assert ST.resolve_approval(
        [_ev("experiment_rejected", eid, {"reason": "no"})], eid).kind == "rejected"
    # empty replacement_changes => plain reject (no runnable change)
    assert ST.resolve_approval(
        [_ev("experiment_rejected", eid, {"replacement_changes": {}})], eid).kind == "rejected"
    # event for a different experiment must not resolve this one
    assert ST.resolve_approval(
        [_ev("experiment_approved", "exp_009", {"edited": False})], eid) is None


# --- pure: instructions -------------------------------------------------------

def test_apply_instructions_bound_hard_rejects():
    """An instruction carrying a structured bound is added to `active` and the
    planner then HARD-REJECTS a violating change (§9.3 / §3)."""
    events = [{
        "type": "instruction_added",
        "payload": {"instruction_id": "instr_001",
                    "text": "Keep dropout low; we are underfitting.",
                    "applies_from": "exp_001",
                    "bound": {"param": "dropout", "op": ">", "value": 0.3}},
    }]
    active, applied = [], set()
    # Not yet applicable at exp_000 (applies_from=exp_001).
    texts = ST.apply_instructions(events, 0, active, applied)
    assert texts == [] and active == []
    # Applicable from exp_001: text biases + bound enters active.
    texts = ST.apply_instructions(events, 1, active, applied)
    assert "Keep dropout low; we are underfitting." in texts
    assert len(active) == 1 and active[0].constraint_id == "instr_001"
    assert active[0].source == "human" and active[0].bound.param == "dropout"
    # Idempotent: a later iteration does not re-add the bound.
    ST.apply_instructions(events, 2, active, applied)
    assert len(active) == 1
    # The planner now rejects dropout=0.5 and proposes a compliant change.
    best = NodeView(id="exp_000", operator="draft", status="success",
                    config={"dropout": 0.25, "learning_rate": 0.01},
                    changes={"dropout": 0.25}, final_metrics={"val_accuracy": 0.88})
    ctx = PlanContext(nodes=[best], constraints=active,
                      allowed_changes=["dropout", "scheduler", "learning_rate"],
                      baseline_config={"dropout": 0.25, "learning_rate": 0.01},
                      objective={"metric": "val_accuracy", "direction": "maximize"},
                      instructions=texts)
    res = propose(ctx, llm=None)
    from app.loop.constraints import violated_constraints
    assert not violated_constraints(res.proposal.changes, active)


def test_apply_instructions_text_only_no_bound():
    events = [{"type": "instruction_added",
               "payload": {"instruction_id": "i2", "text": "Try cosine next."}}]
    active, applied = [], set()
    texts = ST.apply_instructions(events, 5, active, applied)
    assert texts == ["Try cosine next."] and active == []  # no bound => no hard reject


# --- pure: fork detection -----------------------------------------------------

def test_next_pending_fork():
    base = [
        {"type": "branch_created", "branch_id": "branch_x"},
        {"type": "fork_created", "branch_id": "branch_x",
         "parent_experiment_id": "exp_002",
         "payload": {"instruction": "explore high LR",
                     "constraint": {"constraint_id": "f1", "source": "human",
                                    "text": "ban lr>0.05", "applies_to": ["learning_rate"],
                                    "bound": {"param": "learning_rate", "op": ">", "value": 0.05}}}},
    ]
    pf = ST.next_pending_fork(base)
    assert pf is not None and pf.branch_id == "branch_x"
    assert pf.parent_experiment_id == "exp_002"
    assert pf.constraint["constraint_id"] == "f1"
    # Once the branch has an experiment, it is no longer pending.
    busy = base + [{"type": "experiment_proposed", "branch_id": "branch_x",
                    "experiment_id": "exp_003"}]
    assert ST.next_pending_fork(busy) is None
    # A fork without its branch_created is not yet executable.
    assert ST.next_pending_fork([base[1]]) is None
    # No forks at all.
    assert ST.next_pending_fork([{"type": "mission_started", "payload": {}}]) is None


# --- integration helpers ------------------------------------------------------

def _fake_runner_factory(metrics=None):
    """A drop-in for runner.run_experiment: emits started+finished, no training.
    Records every config it was handed so a test can assert the changes ran."""
    metrics = metrics or {"val_accuracy": 0.90, "train_accuracy": 0.91, "runtime_sec": 0.1}
    seen = []

    def fake(*, config_path, workspace_dir, timeout_sec, emit, envelope, **_kw):
        import yaml
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
        seen.append({"experiment_id": envelope.get("experiment_id"), "config": cfg})
        emit("experiment_started",
             {"command": "fake", "workspace_path": workspace_dir, "timeout_sec": timeout_sec},
             **envelope)
        emit("experiment_finished",
             {"status": "success", "final_metrics": dict(metrics), "artifacts": []},
             **envelope)
        return {"status": "success", "final_metrics": dict(metrics),
                "last_metrics": dict(metrics)}

    fake.seen = seen
    return fake


def _write_control(path, **kw):
    """Atomic-ish control write (temp + replace), mirroring the API."""
    body = {"run_state": "run", "approval_required": False}
    body.update(kw)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(body, f)
    os.replace(tmp, path)


def _read_log(events_path):
    if not os.path.exists(events_path):
        return []
    out = []
    with open(events_path) as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _wait_for(pred, events_path, timeout=8.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pred(_read_log(events_path)):
            return True
        time.sleep(0.05)
    return False


_MISSION = {
    "name": "steer-test", "goal": "test",
    "objective": {"metric": "val_accuracy", "direction": "maximize"},
    "adapter": "tiny_cnn",
    "allowed_changes": ["learning_rate", "dropout", "scheduler", "augmentation",
                        "weight_decay"],
    "constraints": [],
}


def _run_mission_bg(mission_id, events_path, max_experiments=2, fake=None):
    """Launch run_mission in a background thread with a fake runner. Returns
    (thread, holder) — holder['err'] is set if the loop raised."""
    if fake is not None:
        RM.RUN.run_experiment = fake
    spec = dict(_MISSION, budget={"max_experiments": max_experiments,
                                  "max_runtime_per_experiment_sec": 5})
    holder = {}

    def go():
        try:
            holder["res"] = RM.run_mission(
                mission_id=mission_id, mission=spec, events_path=events_path)
        except Exception as e:  # pragma: no cover - surfaced via assert
            holder["err"] = repr(e)

    t = threading.Thread(target=go, daemon=True)
    t.start()
    return t, holder


# --- integration: stop --------------------------------------------------------

def test_stop_breaks_the_loop():
    with tempfile.TemporaryDirectory() as d:
        ep = os.path.join(d, "events.jsonl")
        _write_control(os.path.join(d, "control.json"), run_state="stop")
        RM.run_mission(mission_id="m_stop", mission=dict(
            _MISSION, budget={"max_experiments": 3}), events_path=ep)
        log = _read_log(ep)
        types = [e["type"] for e in log]
        assert "experiment_proposed" not in types  # never ran an experiment
        fin = [e for e in log if e["type"] == "mission_finished"]
        assert fin and fin[-1]["payload"]["reason"] == "user_stop"


def test_stop_while_at_approval_gate():
    with tempfile.TemporaryDirectory() as d:
        ep = os.path.join(d, "events.jsonl")
        cp = os.path.join(d, "control.json")
        _write_control(cp, approval_required=True)
        fake = _fake_runner_factory()
        t, holder = _run_mission_bg("m_stopgate", ep, fake=fake)
        # The loop proposes exp_000 and BLOCKS at the gate.
        assert _wait_for(lambda L: any(e["type"] == "experiment_proposed" for e in L), ep)
        time.sleep(0.4)
        assert not fake.seen  # nothing ran while gated
        _write_control(cp, run_state="stop", approval_required=True)
        t.join(timeout=8)
        assert not t.is_alive() and "err" not in holder
        log = _read_log(ep)
        assert not fake.seen  # still never ran the held experiment
        fin = [e for e in log if e["type"] == "mission_finished"]
        assert fin and fin[-1]["payload"]["reason"] == "user_stop"


# --- integration: pause -------------------------------------------------------

def test_pause_blocks_then_resumes():
    with tempfile.TemporaryDirectory() as d:
        ep = os.path.join(d, "events.jsonl")
        cp = os.path.join(d, "control.json")
        _write_control(cp, run_state="pause")
        fake = _fake_runner_factory()
        t, holder = _run_mission_bg("m_pause", ep, max_experiments=1, fake=fake)
        # Paused at the top: no proposal should appear for a while.
        time.sleep(0.6)
        assert not any(e["type"] == "experiment_proposed" for e in _read_log(ep))
        assert t.is_alive()
        # Resume -> it now runs and finishes.
        _write_control(cp, run_state="run")
        t.join(timeout=8)
        assert not t.is_alive() and "err" not in holder
        assert fake.seen  # an experiment ran after resume
        log = _read_log(ep)
        assert any(e["type"] == "mission_finished" for e in log)


# --- integration: approval gate ----------------------------------------------

def _approve_after_proposed(ep, mid, gate_writer, max_experiments=1):
    """Shared driver: launch a 1-experiment approval-gated mission, wait for the
    proposal, run ``gate_writer(exp_id)`` to emit the human decision, join."""
    fake = _fake_runner_factory()
    t, holder = _run_mission_bg(mid, ep, max_experiments=max_experiments, fake=fake)
    assert _wait_for(lambda L: any(e["type"] == "experiment_proposed" for e in L), ep)
    proposed = [e for e in _read_log(ep) if e["type"] == "experiment_proposed"]
    exp_id = proposed[0]["experiment_id"]
    gate_writer(exp_id)
    t.join(timeout=8)
    assert not t.is_alive() and "err" not in holder, holder.get("err")
    return fake, _read_log(ep), exp_id


def test_approval_gate_approve_as_is():
    with tempfile.TemporaryDirectory() as d:
        ep = os.path.join(d, "events.jsonl")
        _write_control(os.path.join(d, "control.json"), approval_required=True)

        def writer(exp_id):
            kun_log("experiment_approved", {"edited": False}, mission_id="m_appr",
                    experiment_id=exp_id, path=ep,
                    actor={"type": "human", "name": "user"})

        fake, log, exp_id = _approve_after_proposed(ep, "m_appr", writer)
        assert any(s["experiment_id"] == exp_id for s in fake.seen)  # it ran


def test_approval_gate_approve_edited_runs_human_changes():
    with tempfile.TemporaryDirectory() as d:
        ep = os.path.join(d, "events.jsonl")
        _write_control(os.path.join(d, "control.json"), approval_required=True)

        def writer(exp_id):
            kun_log("experiment_approved",
                    {"edited": True, "changes": {"learning_rate": 0.005}},
                    mission_id="m_edit", experiment_id=exp_id, path=ep,
                    actor={"type": "human", "name": "user"})

        fake, log, exp_id = _approve_after_proposed(ep, "m_edit", writer)
        ran = [s for s in fake.seen if s["experiment_id"] == exp_id]
        assert ran and ran[0]["config"]["learning_rate"] == 0.005  # human edit ran


def test_approval_gate_reject_with_replacement_runs_replacement():
    with tempfile.TemporaryDirectory() as d:
        ep = os.path.join(d, "events.jsonl")
        _write_control(os.path.join(d, "control.json"), approval_required=True)

        def writer(exp_id):
            kun_log("experiment_rejected",
                    {"reason": "too high", "replacement_changes": {"dropout": 0.2}},
                    mission_id="m_repl", experiment_id=exp_id, path=ep,
                    actor={"type": "human", "name": "user"})

        fake, log, exp_id = _approve_after_proposed(ep, "m_repl", writer)
        ran = [s for s in fake.seen if s["experiment_id"] == exp_id]
        assert ran and ran[0]["config"]["dropout"] == 0.2  # replacement ran


def test_approval_gate_reject_no_replacement_marks_rejected():
    with tempfile.TemporaryDirectory() as d:
        ep = os.path.join(d, "events.jsonl")
        _write_control(os.path.join(d, "control.json"), approval_required=True)

        def writer(exp_id):
            kun_log("experiment_rejected", {"reason": "no good"},
                    mission_id="m_rej", experiment_id=exp_id, path=ep,
                    actor={"type": "human", "name": "user"})

        fake, log, exp_id = _approve_after_proposed(ep, "m_rej", writer)
        # The held experiment never ran...
        assert not any(s["experiment_id"] == exp_id for s in fake.seen)
        # ...and a reject decision was recorded for it.
        decs = [e for e in log if e["type"] == "decision_created"
                and e.get("experiment_id") == exp_id]
        assert decs and decs[0]["payload"]["decision"] == "reject"


# --- integration: fork execution ---------------------------------------------

def test_fork_executes_on_new_branch():
    with tempfile.TemporaryDirectory() as d:
        ep = os.path.join(d, "events.jsonl")
        fake = _fake_runner_factory()
        RM.RUN.run_experiment = fake
        # Run a short normal mission first so exp_000 exists to fork from.
        RM.run_mission(mission_id="m_fork", mission=dict(
            _MISSION, budget={"max_experiments": 1}), events_path=ep)
        assert any(s["experiment_id"] == "exp_000" for s in fake.seen)
        # Record a fork off exp_000 onto branch_fork (as the API would).
        kun_log("branch_created", {"name": "fork", "reason": "probe", "source": "human"},
                mission_id="m_fork", branch_id="branch_fork",
                parent_experiment_id="exp_000", path=ep)
        kun_log("fork_created",
                {"instruction": "raise dropout", "reason": "probe",
                 "constraint": {"constraint_id": "fk1", "source": "human",
                                "text": "ban lr>0.02", "applies_to": ["learning_rate"],
                                "bound": {"param": "learning_rate", "op": ">", "value": 0.02}}},
                mission_id="m_fork", branch_id="branch_fork",
                parent_experiment_id="exp_000", path=ep,
                actor={"type": "human", "name": "user"})
        # Resume the loop: it should detect the pending fork and run one
        # experiment on branch_fork off exp_000.
        before = len(fake.seen)
        RM.run_mission(mission_id="m_fork", mission=dict(
            _MISSION, budget={"max_experiments": 2}), events_path=ep)
        log = _read_log(ep)
        fork_props = [e for e in log if e["type"] == "experiment_proposed"
                      and e.get("branch_id") == "branch_fork"]
        assert fork_props, "expected an experiment proposed on the fork branch"
        assert fork_props[0]["parent_experiment_id"] == "exp_000"
        assert len(fake.seen) > before  # the fork experiment actually ran


def _run_all():
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")


if __name__ == "__main__":
    _run_all()
