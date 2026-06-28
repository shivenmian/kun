"""run_mission — the Mode-A autonomous loop entry point (callable + CLI).

Drives planner -> patcher -> runner -> (constraint generator) -> evaluator ->
decider, emitting ALL events through ``kun_log`` to runs/<mission_id>/events.jsonl
in the same shape/order as examples/replays/sample.events.jsonl.

This is the seam W1's POST /missions/{id}/start hook (and the lead's integration)
invokes:

    from app.loop.run_mission import run_mission
    run_mission(mission_id="mission_x", mission=<dict|path|None>, events_path=None)

CLI:
    cd backend && python -m app.loop.run_mission --mission-id mission_x
    python backend/app/loop/run_mission.py --mission-id mission_x
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Union

import yaml

# --- make `kun` (repo root) and `app` importable regardless of entry point ----
_THIS = os.path.abspath(__file__)
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(_THIS), "..", "..", ".."))
BACKEND_ROOT = os.path.join(REPO_ROOT, "backend")
for p in (REPO_ROOT, BACKEND_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from kun.log import kun_log  # noqa: E402

from app.loop import constraints as C  # noqa: E402
from app.loop import memory_writer as MW  # noqa: E402
from app.loop import evaluator as EV  # noqa: E402
from app.loop import decider as DEC  # noqa: E402
from app.loop import planner as PL  # noqa: E402
from app.loop import runner as RUN  # noqa: E402
from app.loop.llm_client import LLMClient  # noqa: E402
from app.loop.patcher import (  # noqa: E402
    agent_edit,
    apply_config_patch,
    select_patcher,
)
from app.loop.schemas import Constraint  # noqa: E402
from app.loop import steering as ST  # noqa: E402

BRANCH_MAIN = "branch_main"

# Control-file poll cadence (s) and approval-gate wall-clock cap (s). The cap is
# advisory: on timeout the loop KEEPS waiting and logs — it never auto-approves
# (a forgotten gate must not silently run an unreviewed experiment).
STEER_POLL_SEC = float(os.environ.get("KUN_STEER_POLL_SEC", "0.25"))
APPROVAL_TIMEOUT_SEC = float(os.environ.get("KUN_APPROVAL_TIMEOUT_SEC", "1800"))
DEFAULT_MISSION_YAML = os.path.join(REPO_ROOT, "examples", "tiny_cnn", "mission.yaml")
BASELINE_CONFIG = os.path.join(REPO_ROOT, "examples", "tiny_cnn", "config.yaml")


class Emitter:
    """Wraps kun_log with the per-mission path + mission_id baked in."""

    def __init__(self, mission_id: str, path: str):
        self.mission_id = mission_id
        self.path = path

    def __call__(self, event_type: str, payload: Dict[str, Any], **env) -> Dict[str, Any]:
        return kun_log(
            event_type, payload, mission_id=self.mission_id, path=self.path, **env
        )


def _rel(path: str) -> str:
    return os.path.relpath(path, REPO_ROOT)


def _read_existing(events_path: str) -> List[Dict[str, Any]]:
    """Read events already in the log (empty list if none) — for idempotent lifecycle."""
    if not os.path.exists(events_path):
        return []
    out: List[Dict[str, Any]] = []
    with open(events_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _wait_while_paused(control_path: str, mission_id: str,
                       poll: float = STEER_POLL_SEC) -> str:
    """Block while ``run_state == pause`` (CONTRACT §9.2). Returns the final
    run_state once it leaves pause: ``"run"`` (resume) or ``"stop"``."""
    announced = False
    while True:
        ctl = ST.read_control(control_path)
        if ctl["run_state"] != "pause":
            if announced:
                print(f"[run_mission] {mission_id} resumed "
                      f"(run_state={ctl['run_state']})", flush=True)
            return ctl["run_state"]
        if not announced:
            print(f"[run_mission] {mission_id} PAUSED; polling control.json "
                  "for resume/stop...", flush=True)
            announced = True
        time.sleep(poll)


def _wait_for_approval(events_path: str, control_path: str, exp_id: str,
                       mission_id: str, poll: float = STEER_POLL_SEC,
                       timeout_sec: float = APPROVAL_TIMEOUT_SEC) -> ST.ApprovalOutcome:
    """Block at the approval gate for ``exp_id`` until the human approves/rejects
    it (read from the log) — honoring stop/pause via the control file the whole
    time (CONTRACT §9.2/§9.3). On the wall-clock cap it logs but KEEPS waiting;
    it never auto-approves. Returns an :class:`ST.ApprovalOutcome` (``kind`` may
    be ``"stop"`` if the control file asked the loop to stop while waiting)."""
    print(f"[run_mission] {mission_id} approval gate: holding {exp_id}, "
          "awaiting approve/reject...", flush=True)
    t0 = time.time()
    warned = 0.0
    paused = False
    while True:
        ctl = ST.read_control(control_path)
        if ctl["run_state"] == "stop":
            return ST.ApprovalOutcome("stop")
        if ctl["run_state"] == "pause":
            if not paused:
                print(f"[run_mission] {mission_id} paused while holding {exp_id}.",
                      flush=True)
                paused = True
            time.sleep(poll)
            continue
        paused = False
        outcome = ST.resolve_approval(_read_existing(events_path), exp_id)
        if outcome is not None:
            print(f"[run_mission] {mission_id} approval gate: {exp_id} -> "
                  f"{outcome.kind}", flush=True)
            return outcome
        elapsed = time.time() - t0
        if elapsed > timeout_sec and elapsed - warned >= timeout_sec:
            print(f"[run_mission] {mission_id} approval for {exp_id} still pending "
                  f"after {int(elapsed)}s — NOT auto-approving; still waiting.",
                  flush=True)
            warned = elapsed
        time.sleep(poll)


def _load_mission(mission: Union[Dict[str, Any], str, None]) -> Dict[str, Any]:
    if isinstance(mission, dict):
        return mission
    path = mission or DEFAULT_MISSION_YAML
    with open(path) as f:
        return yaml.safe_load(f)


def _agent_actor(name: str, model: str) -> Dict[str, Any]:
    return {"type": "agent", "name": name, "model": model}


def run_mission(
    *,
    mission_id: str,
    mission: Union[Dict[str, Any], str, None] = None,
    events_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the full Mode-A loop. Returns the mission_finished payload."""
    # The control file + per-experiment workspaces live alongside the event log.
    # With no explicit events_path this is the conventional runs/<id>/ (P0
    # unchanged); when one is given (tests/integration) everything is colocated
    # in its directory so a temp dir is fully self-contained.
    if events_path:
        runs_dir = os.path.dirname(os.path.abspath(events_path))
    else:
        runs_dir = os.path.join(REPO_ROOT, "runs", mission_id)
        events_path = os.path.join(runs_dir, "events.jsonl")
    os.makedirs(runs_dir, exist_ok=True)
    control_path = os.path.join(runs_dir, "control.json")

    # When started via the API (POST /missions then /start), the event log already
    # holds mission_created/mission_started — read what's there so we don't double-emit
    # and so we can recover the mission spec the API recorded. Standalone CLI runs see
    # an empty log and emit everything from mission.yaml. (CONTRACT: log is source of truth.)
    existing = _read_existing(events_path)
    existing_types = {e.get("type") for e in existing}
    if mission is None:
        for e in existing:
            if e.get("type") == "mission_created":
                mission = e.get("payload")  # prefer the spec the API recorded
                break

    spec = _load_mission(mission)
    model = spec.get("model", "claude-opus-4-8")
    objective = spec.get("objective", {"metric": "val_accuracy", "direction": "maximize"})
    metric = objective.get("metric", "val_accuracy")
    direction = objective.get("direction", "maximize")
    budget = spec.get("budget", {})
    max_experiments = int(budget.get("max_experiments", 8))
    timeout_sec = int(budget.get("max_runtime_per_experiment_sec", 90))
    target = objective.get("target")
    allowed_changes = spec.get("allowed_changes", [])

    # --- patcher selection (pluggable; doc 08 §1/§7) -------------------------
    # Default = config-patch (P0 unchanged). agent-edit edits the mission's
    # editable_files (copied out of examples/<adapter>/ into a per-experiment
    # sandbox); any flake falls back to config-patch for that experiment.
    patcher_name = select_patcher(spec)
    editable_files = spec.get("editable_files", []) or []
    adapter = spec.get("adapter", "tiny_cnn")
    source_dir = os.path.join(REPO_ROOT, "examples", adapter)
    editor_model = os.environ.get("KUN_EDITOR_MODEL", "sonnet")

    with open(BASELINE_CONFIG) as f:
        baseline_config = yaml.safe_load(f)

    emit = Emitter(mission_id, events_path)

    llm = LLMClient(model)
    path_kind = "LLM" if llm.available() else "heuristic"
    print(f"[run_mission] {mission_id} driver={path_kind} model={model} "
          f"patcher={patcher_name}", flush=True)

    # --- mission_created + mission_started (idempotent — skip if already in the log) ---
    if "mission_created" not in existing_types:
        emit("mission_created", spec)
    if "mission_started" not in existing_types:
        emit("mission_started", {"mode": "live", "started_by": "user"},
             actor={"type": "human", "name": "user"})

    # --- seed human constraints (canonical objects) into memory ---
    active: List[Constraint] = []
    seed_constraints = "constraint_added" not in existing_types
    for raw in spec.get("constraints", []) or []:
        try:
            c = Constraint.model_validate(raw)
        except Exception:
            continue
        active.append(c)
        if seed_constraints:
            emit("constraint_added", c.to_payload(), branch_id=BRANCH_MAIN,
                 actor={"type": "human", "name": "user"})

    nodes: List[PL.NodeView] = []
    soft_lessons: List[Constraint] = []  # SOFT tier (no bound) — bias-only
    learned_counter = 0
    best_value: Optional[float] = None
    best_id: Optional[str] = None
    stop_reason = "max_experiments_reached"

    def emit_hard_learned(factory, exp_id: str) -> Constraint:
        """Build a hard learned constraint, MERGE it into memory (tighten bound +
        grow confidence instead of duplicating), and emit it. ``factory`` takes the
        candidate constraint_id and returns the Constraint. A new constraint
        consumes the next learned_NNN id; a merge reuses the existing id so the
        memory panel shows ONE sharpened constraint (state is keyed by id)."""
        nonlocal learned_counter
        candidate_id = f"learned_{learned_counter + 1:03d}"
        candidate = factory(candidate_id)
        merged, was_merged = C.merge_learned_constraint(active, candidate)
        if not was_merged:
            learned_counter += 1
        emit("constraint_learned", merged.to_payload(),
             experiment_id=exp_id, branch_id=BRANCH_MAIN)
        return merged

    exp_i = 0
    # Instruction ids whose structured `bound` has already been folded into
    # `active` (so a persistent instruction is not re-added each iteration).
    applied_instruction_ids: set = set()
    while exp_i < max_experiments:
        # --- live steering: control file at the TOP of every iteration (§9.2) ---
        # No control file => default {run, no-approval} => P0 path is unchanged.
        control = ST.read_control(control_path)
        if control["run_state"] == "stop":
            stop_reason = "user_stop"
            print(f"[run_mission] {mission_id} stop requested -> finishing.",
                  flush=True)
            break
        if control["run_state"] == "pause":
            if _wait_while_paused(control_path, mission_id) == "stop":
                stop_reason = "user_stop"
                break
            control = ST.read_control(control_path)  # re-read post-resume

        exp_id = f"exp_{exp_i:03d}"

        # --- mid-run instructions (§9.3): soft-bias texts + hard bounds -------
        log_events = _read_existing(events_path)
        instr_texts = ST.apply_instructions(
            log_events, exp_i, active, applied_instruction_ids
        )

        # --- live fork execution (Mode A, §9.3) ------------------------------
        # An executable fork = a fork_created branch (with its branch_created)
        # that has no experiments yet AND whose parent node we have run. Run the
        # next proposal there, pinning the parent + applying any forked bound.
        branch_id = BRANCH_MAIN
        force_parent_id: Optional[str] = None
        ctx_constraints = active
        pending = ST.next_pending_fork(log_events)
        if pending is not None and any(
            n.id == pending.parent_experiment_id for n in nodes
        ):
            branch_id = pending.branch_id
            force_parent_id = pending.parent_experiment_id
            fork_bound: Optional[Constraint] = None
            if pending.constraint:
                try:
                    fork_bound = Constraint.model_validate(pending.constraint)
                except Exception:
                    fork_bound = None
            ctx_constraints = active + ([fork_bound] if fork_bound else [])
            print(f"[run_mission] {mission_id} executing fork on {branch_id} "
                  f"off {force_parent_id} (constraint={fork_bound.constraint_id if fork_bound else None})",
                  flush=True)

        ctx = PL.PlanContext(
            nodes=nodes, constraints=ctx_constraints, allowed_changes=allowed_changes,
            baseline_config=baseline_config, objective=objective,
            soft_lessons=soft_lessons, instructions=instr_texts,
            branch_id=branch_id, force_parent_id=force_parent_id,
        )
        res = PL.propose(ctx, llm=llm)
        prop = res.proposal

        # Exhausted, constraint-respecting search space -> stop cleanly.
        if not prop.changes and prop.operator != "draft":
            stop_reason = "search_exhausted"
            break

        parent_id = res.parent_id
        parent_config = res.parent_config
        env = {"experiment_id": exp_id, "branch_id": branch_id,
               "parent_experiment_id": parent_id}

        # --- experiment_proposed ---
        prop_payload = {
            "operator": prop.operator,
            "hypothesis": prop.hypothesis,
            "changes": prop.changes,
            "expected_outcome": prop.expected_outcome,
            "risk": prop.risk,
            "rationale": prop.rationale,
        }
        emit("experiment_proposed", prop_payload, actor=_agent_actor("planner", model), **env)
        if res.rejected_candidates:
            print(f"[planner] {exp_id} hard-rejected (bound): "
                  f"{res.rejected_candidates} -> chose {prop.changes}", flush=True)

        # --- approval gate (§9.3): hold the proposed node until a human acts ---
        if control["approval_required"]:
            outcome = _wait_for_approval(events_path, control_path, exp_id, mission_id)
            if outcome.kind == "stop":
                stop_reason = "user_stop"
                break
            if outcome.kind == "rejected":
                # Human rejected with no replacement -> mark the node rejected
                # and move on to the next proposal (do NOT run it).
                emit("decision_created",
                     {"decision": "reject",
                      "rationale": "Rejected by human at the approval gate.",
                      "next_action": {"type": "propose_next_experiment",
                                      "parent_experiment_id": best_id}},
                     actor={"type": "human", "name": "user"}, **env)
                nodes.append(PL.NodeView(
                    id=exp_id, operator=prop.operator, status="rejected",
                    config={**parent_config, **prop.changes}, changes=prop.changes,
                    parent_id=parent_id, branch_id=branch_id,
                ))
                exp_i += 1
                continue
            if outcome.kind in ("approved_edited", "rejected_replacement"):
                # Run the human's changes verbatim (human authority overrides the
                # planner; a replacement is recorded as a human `improve`).
                prop.changes = outcome.changes or {}
                if outcome.kind == "rejected_replacement":
                    prop.operator = "improve"
                prop_payload["changes"] = prop.changes
                prop_payload["operator"] = prop.operator

        # --- patch + file_diff_created ---
        # config-patch ALWAYS runs: it writes the config.yaml the runner consumes
        # (runner unchanged) AND is the fallback diff. When agent-edit is selected
        # we additionally edit real code in an isolated sandbox and, on success,
        # emit THAT real diff instead of the config diff (doc 08).
        workspace = os.path.join(runs_dir, exp_id)
        if parent_id is None:
            base_label = _rel(BASELINE_CONFIG)
        else:
            base_label = _rel(os.path.join(runs_dir, parent_id, "config.yaml"))
        new_label = _rel(os.path.join(workspace, "config.yaml"))
        config_path, config_diff, _ = apply_config_patch(
            base_config=parent_config, changes=prop.changes,
            workspace_dir=workspace, base_file_path=base_label, new_file_path=new_label,
        )

        diff_payload = {
            "file_path": new_label, "base_file_path": base_label, "diff": config_diff,
        }
        if patcher_name == "agent-edit":
            edit_ws = os.path.join(workspace, "edit")
            pr = agent_edit.apply(
                edit_ws, prop, ctx_constraints, editable_files, editor_model,
                source_dir=source_dir,
            )
            if pr.ok:
                first = pr.files_changed[0] if pr.files_changed else (
                    editable_files[0] if editable_files else "edited"
                )
                diff_payload = {
                    "file_path": _rel(os.path.join(edit_ws, first)),
                    "base_file_path": os.path.join(_rel(source_dir), first),
                    "diff": pr.diff,
                    "files_changed": pr.files_changed,
                    "patcher": "agent-edit",
                    "commit_sha": pr.commit_sha,
                    "editor_cost_usd": pr.cost_usd,
                    "editor_session_id": pr.session_id,
                }
                print(f"[patcher] {exp_id} agent-edit OK files={pr.files_changed} "
                      f"cost={pr.cost_usd}", flush=True)
            else:
                # Flake (no key/timeout/no-diff/out-of-scope/broken) -> fall back
                # to config-patch for THIS experiment; loop keeps running (§7).
                print(f"[patcher] {exp_id} agent-edit FAILED ({pr.error}) -> "
                      "falling back to config-patch.", flush=True)
        emit("file_diff_created", diff_payload,
             experiment_id=exp_id, branch_id=branch_id)

        # --- run (emits experiment_started, metric_logged*, finished/failed) ---
        result = RUN.run_experiment(
            config_path=config_path, workspace_dir=workspace,
            timeout_sec=timeout_sec, emit=emit, envelope=env,
        )

        full_config = dict(parent_config)
        full_config.update(prop.changes)
        parent_metrics = next(
            (n.final_metrics for n in nodes if n.id == parent_id), {}
        )

        # --- closed constraint loop: NaN -> deterministic constraint_learned ---
        if result["status"] == "failed" and result.get("failure_type") == "nan_detected":
            lr = float(full_config.get("learning_rate", 0.0))
            constraint = emit_hard_learned(
                lambda cid: C.learn_constraint_from_nan(
                    lr_at_failure=lr, experiment_id=exp_id, constraint_id=cid,
                ),
                exp_id,
            )
            print(f"[constraint] {exp_id} NaN at lr={lr} -> {constraint.constraint_id} "
                  f"bans learning_rate > {constraint.bound.value} "
                  f"(confidence={constraint.confidence})", flush=True)

        # --- underfitting -> deterministic dropout/reg bound (sample's learned_002) ---
        if result["status"] == "success":
            hit = C.detect_underfit_param(
                changes=prop.changes, parent_config=parent_config,
                parent_metrics=parent_metrics,
                child_metrics=result.get("final_metrics", {}), metric=metric,
            )
            if hit is not None:
                uf_param, uf_value = hit
                constraint = emit_hard_learned(
                    lambda cid: C.learn_constraint_from_underfit(
                        param=uf_param, value_at_underfit=uf_value,
                        experiment_id=exp_id, constraint_id=cid,
                    ),
                    exp_id,
                )
                print(f"[constraint] {exp_id} underfit at {uf_param}={uf_value} -> "
                      f"{constraint.constraint_id} bans {uf_param} > "
                      f"{constraint.bound.value} (confidence={constraint.confidence})",
                      flush=True)

        # --- evaluate ---
        evaluation = EV.evaluate(
            result=result, changes=prop.changes, objective=objective,
            prev_best=best_value, llm=llm,
        )
        eval_payload = {
            "verdict": evaluation.verdict,
            "summary": evaluation.summary,
            "evidence": evaluation.evidence,
            "concerns": evaluation.concerns,
        }
        emit("evaluation_created", eval_payload,
             actor=_agent_actor("evaluator", model),
             experiment_id=exp_id, branch_id=branch_id)

        # --- record node + update best ---
        node = PL.NodeView(
            id=exp_id, operator=prop.operator, status=result["status"],
            config=full_config, changes=prop.changes,
            final_metrics=result.get("final_metrics", {}),
            failure_type=result.get("failure_type"), parent_id=parent_id,
            branch_id=branch_id,
        )
        nodes.append(node)
        prev_best_value = best_value
        val = None
        if result["status"] == "success":
            val = result.get("final_metrics", {}).get(metric)
            if val is not None:
                better = (best_value is None or
                          (val > best_value if direction == "maximize" else val < best_value))
                if better:
                    best_value, best_id = val, exp_id

        # --- decide ---
        decision = DEC.decide(
            evaluation=evaluation, result=result, experiment_id=exp_id,
            best_valid_id=best_id,
        )
        emit("decision_created",
             {"decision": decision.decision, "rationale": decision.rationale,
              "next_action": decision.next_action.model_dump()},
             experiment_id=exp_id, branch_id=branch_id)

        # --- positive Σ-summary: promote with a real metric gain -> SOFT lesson ---
        if (decision.decision == "promote" and val is not None
                and prev_best_value is not None and prop.changes):
            improvement = (val - prev_best_value if direction == "maximize"
                           else prev_best_value - val)
            if improvement > 0:
                learned_counter += 1
                lesson = C.soft_lesson_from_promotion(
                    changes=prop.changes, metric=metric, delta=improvement,
                    experiment_id=exp_id,
                    constraint_id=f"learned_{learned_counter:03d}",
                )
                soft_lessons.append(lesson)
                emit("constraint_learned", lesson.to_payload(),
                     experiment_id=exp_id, branch_id=BRANCH_MAIN)
                print(f"[lesson] {exp_id} promote -> soft lesson "
                      f"{lesson.constraint_id}: {lesson.text}", flush=True)

        exp_i += 1

        # --- stop on target reached ---
        if target is not None and best_value is not None:
            hit = (best_value >= target if direction == "maximize"
                   else best_value <= target)
            if hit:
                stop_reason = "target_metric_reached"
                break

    # --- GATED LLM memory-writer (doc 11 #4): distill durable SOFT lessons -----
    # Purely additive, soft-tier only, and OFF unless KUN_MEMORY_WRITER=1 (so the
    # deterministic demo is byte-for-byte unchanged). Any flake -> no-op ([]),
    # never raises into the loop. Emitted as constraint_learned with NO bound,
    # identical in shape to the deterministic Σ-summary soft lessons above.
    if MW.enabled(llm):
        try:
            distilled = MW.distill_soft_lessons(
                nodes=nodes, existing_lessons=soft_lessons, llm=llm,
                id_start=learned_counter,
            )
        except Exception:
            distilled = []
        for lesson in distilled:
            learned_counter += 1
            soft_lessons.append(lesson)
            lesson_env = {"branch_id": BRANCH_MAIN}
            if best_id is not None:
                lesson_env["experiment_id"] = best_id
            emit("constraint_learned", lesson.to_payload(), **lesson_env)
            print(f"[memory-writer] distilled soft lesson "
                  f"{lesson.constraint_id}: {lesson.text}", flush=True)

    finished = {
        "status": "completed",
        "reason": stop_reason,
        "best_experiment_id": best_id,
        "best_metric": {"name": metric, "value": best_value},
    }
    emit("mission_finished", finished)
    print(f"[run_mission] done: {finished}", flush=True)
    return finished


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run a Kun Mode-A tiny-CNN mission.")
    # Positional form is what the API's /start subprocess seam uses:
    #   python -m app.loop.run_mission <mission_id> [mode]
    # Flag form (--mission-id) is kept for standalone/manual runs.
    ap.add_argument("mission_id_pos", nargs="?", default=None,
                    help="Mission id (positional; used by the API /start seam).")
    ap.add_argument("mode_pos", nargs="?", default=None,
                    help="Mode (positional, accepted but unused — Mode A is implied).")
    ap.add_argument("--mission-id", dest="mission_id", default=None)
    ap.add_argument("--mission", default=None,
                    help="Path to mission.yaml (default: examples/tiny_cnn/mission.yaml)")
    ap.add_argument("--events-path", default=None)
    args = ap.parse_args(argv)
    mission_id = args.mission_id or args.mission_id_pos
    if not mission_id:
        ap.error("mission id required (positional or --mission-id)")
    run_mission(mission_id=mission_id, mission=args.mission,
                events_path=args.events_path)


if __name__ == "__main__":
    main()
