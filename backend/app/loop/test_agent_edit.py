"""Tests + real-cycle driver for the agent-edit patcher (doc 08).

Cheap tests (no API spend) run always:
  - patcher selection (mission / env / default / unknown).
  - fallback triggers: empty editable_files, no API key (monkeypatched).
  - the loop's fallback semantics (ok=False -> config-patch diff is used).

The REAL cycle (costs ~$0.03) runs only when invoked directly with --real (or
KUN_RUN_REAL_EDIT=1): it seeds a throwaway sandbox with a real .py file, asks the
coding agent for ONE tiny atomic edit, and asserts a non-empty diff containing
the change.

    cd backend && source .venv/bin/activate && python app/loop/test_agent_edit.py        # cheap only
    cd backend && source .venv/bin/activate && python app/loop/test_agent_edit.py --real  # + real cycle
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.abspath(os.path.join(_HERE, "..", ".."))
_REPO = os.path.abspath(os.path.join(_BACKEND, ".."))
for p in (_REPO, _BACKEND):
    if p not in sys.path:
        sys.path.insert(0, p)

from app.loop import patcher as P  # noqa: E402
from app.loop.schemas import Constraint, Proposal  # noqa: E402


# --- selection ---------------------------------------------------------------

def test_select_default_config_patch():
    os.environ.pop("KUN_PATCHER", None)
    assert P.select_patcher(None) == "config-patch"
    assert P.select_patcher({}) == "config-patch"


def test_select_mission_agent_edit():
    os.environ.pop("KUN_PATCHER", None)
    assert P.select_patcher({"patcher": "agent-edit"}) == "agent-edit"
    assert P.select_patcher({"patcher": "config-patch"}) == "config-patch"


def test_select_env_override():
    os.environ["KUN_PATCHER"] = "agent-edit"
    try:
        assert P.select_patcher({"patcher": "config-patch"}) == "agent-edit"
    finally:
        os.environ.pop("KUN_PATCHER", None)


def test_select_unknown_falls_back():
    os.environ.pop("KUN_PATCHER", None)
    assert P.select_patcher({"patcher": "bogus"}) == "config-patch"


# --- fallback triggers (no API spend) ----------------------------------------

def test_empty_editable_files_fails():
    with tempfile.TemporaryDirectory() as d:
        pr = P.agent_edit.apply(
            os.path.join(d, "ws"),
            Proposal(operator="improve", hypothesis="x", changes={}, rationale="r"),
            [], [], "sonnet", source_dir=d,
        )
        assert pr.ok is False
        assert "editable_files" in (pr.error or "")


def test_no_api_key_fails(monkeypatch_key=None):
    # Force the no-key branch without touching the real env file.
    orig = P._ensure_api_key
    P._ensure_api_key = lambda: False  # type: ignore
    try:
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "src")
            os.makedirs(src)
            with open(os.path.join(src, "m.py"), "w") as f:
                f.write("LR = 0.01\n")
            pr = P.agent_edit.apply(
                os.path.join(d, "ws"),
                Proposal(operator="improve", hypothesis="x", changes={}, rationale="r"),
                [], ["m.py"], "sonnet", source_dir=src,
            )
            assert pr.ok is False
            assert "ANTHROPIC_API_KEY" in (pr.error or "")
    finally:
        P._ensure_api_key = orig  # type: ignore


def test_loop_fallback_semantics():
    # Mirror run_mission's branch: when agent-edit returns ok=False, the emitted
    # diff_payload must remain the config-patch diff (loop keeps running, §7).
    config_diff = "--- a\n+++ b\n-learning_rate: 0.01\n+learning_rate: 0.003\n"
    diff_payload = {"diff": config_diff, "file_path": "config.yaml"}
    pr = P.PatchResult(ok=False, error="editor timed out")
    if pr.ok:  # would override with the real diff
        diff_payload = {"diff": pr.diff, "patcher": "agent-edit"}
    assert diff_payload["diff"] == config_diff
    assert "patcher" not in diff_payload  # fell back -> config-patch


def test_build_prompt_has_discipline_and_surface():
    prompt = P.build_edit_prompt(
        Proposal(operator="improve", hypothesis="lower lr",
                 changes={"learning_rate": 0.003}, rationale="stabilise"),
        [Constraint(constraint_id="learned_001", source="learned",
                    text="high lr diverges",
                    bound={"param": "learning_rate", "op": ">", "value": 0.01})],
        ["train.py"],
    )
    assert "exactly ONE atomic change" in prompt
    assert "train.py" in prompt
    assert "Do NOT set learning_rate > 0.01" in prompt
    assert "Do NOT run training" in prompt


# --- the REAL cycle (costs ~$0.03) -------------------------------------------

def real_cycle():
    """Seed a sandbox with a real .py file, ask for ONE atomic edit, assert diff."""
    model = os.environ.get("KUN_EDITOR_MODEL", "sonnet")
    work = tempfile.mkdtemp(prefix="kun_agent_edit_")
    try:
        src = os.path.join(work, "src")
        os.makedirs(src)
        py = os.path.join(src, "model.py")
        with open(py, "w") as f:
            f.write(
                "# Tiny model config.\n"
                "DEFAULT_LEARNING_RATE = 0.01\n"
                "DROPOUT = 0.25\n\n"
                "def make_optimizer(params):\n"
                "    return ('adam', DEFAULT_LEARNING_RATE)\n"
            )
        prop = Proposal(
            operator="improve",
            hypothesis="A lower learning rate should stabilise training.",
            changes={"DEFAULT_LEARNING_RATE": 0.003},
            expected_outcome="More stable training.",
            risk="low",
            rationale="Lower the default learning-rate constant.",
        )
        print(f"[real] invoking agent-edit model={model} ...", flush=True)
        print("------ EDIT PROMPT ------")
        print(P.build_edit_prompt(prop, [], ["model.py"]))
        print("-------------------------")
        pr = P.agent_edit.apply(
            os.path.join(work, "ws"), prop, [], ["model.py"], model, source_dir=src,
        )
        print(f"[real] ok={pr.ok} error={pr.error} cost_usd={pr.cost_usd} "
              f"session={pr.session_id} commit={pr.commit_sha}", flush=True)
        print("------ CAPTURED DIFF ------")
        print(pr.diff)
        print("---------------------------")
        assert pr.ok, f"expected ok=True, got error={pr.error}"
        assert pr.diff.strip(), "expected a non-empty diff"
        assert "DEFAULT_LEARNING_RATE" in pr.diff, "diff should touch the constant"
        assert "0.003" in pr.diff, "diff should contain the new value"
        assert pr.files_changed == ["model.py"], pr.files_changed
        print("PASS real_cycle")
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _run_cheap():
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} cheap tests passed.")


if __name__ == "__main__":
    _run_cheap()
    if "--real" in sys.argv or os.environ.get("KUN_RUN_REAL_EDIT") == "1":
        real_cycle()
