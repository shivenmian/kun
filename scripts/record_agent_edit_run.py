"""Record a GENUINE agent-edit autoresearch run (DoD #6, honest).

This drives Kun's MERGED agent-edit patcher (``backend/app/loop/patcher.py``,
i.e. the Claude Code CLI run headless as a coding-agent subprocess) to edit the
REAL code of a tiny CPU-only target (``examples/replays/agent_edit_target/target.py``)
across a few experiments, then EXECUTES each edited copy to capture the REAL
accuracy, and emits genuine Kun events to
``examples/replays/agent_edit_real.events.jsonl`` via ``kun_log``.

Everything recorded is real: the diffs are the actual ``git diff`` of what the
coding agent changed; the metrics are the actual stdout of running the edited
code on CPU (no GPU, no torch). If a real edit flakes or regresses, it is
recorded as-is -- numbers are never faked. See
``examples/replays/agent_edit_real.README.md`` for the honesty guard.

Usage:
    python scripts/record_agent_edit_run.py
    KUN_EDITOR_MODEL=haiku python scripts/record_agent_edit_run.py   # cheap editor

The arc (designed so >=1 edit genuinely improves the metric, with a clear best
node), on a concentric-circles classification task where a LINEAR hidden layer
is stuck near chance:

    exp_000  draft    baseline (identity activation, HIDDEN_SIZE=3) -- run as-is
    exp_001  improve  activation: identity -> np.tanh  (the dominant lever)
    exp_002  improve  HIDDEN_SIZE: 3 -> 8              (more capacity)
    exp_003  improve  HIDDEN_SIZE: 8 -> 16             (more capacity)

Edits ACCUMULATE: each experiment's source_dir is the previous experiment's
edited workspace, so each captured diff is a single, clean, code-level change.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

# --- make backend + repo importable (run with the main venv) ------------------
_THIS = os.path.abspath(__file__)
_REPO = os.path.dirname(os.path.dirname(_THIS))          # repo root (worktree)
_BACKEND = os.path.join(_REPO, "backend")
for p in (_REPO, _BACKEND):
    if p not in sys.path:
        sys.path.insert(0, p)

from app.loop.patcher import agent_edit          # MERGED patcher (read-only use)
from kun.log import kun_log                        # the only emit helper

# --- constants ----------------------------------------------------------------
MISSION_ID = "agent_edit_real"
OUT_PATH = os.path.join(_REPO, "examples", "replays", "agent_edit_real.events.jsonl")
TARGET_DIR = os.path.join(_REPO, "examples", "replays", "agent_edit_target")
EDITABLE = ["target.py"]
EDITOR_MODEL = os.environ.get("KUN_EDITOR_MODEL", "haiku")
RUN_TIMEOUT_SEC = 60
METRIC_RE = re.compile(r"METRIC\s+accuracy=([0-9.]+|nan)", re.I)

PLANNER = {"type": "agent", "name": "planner", "model": "claude-opus-4-8"}
EVALUATOR = {"type": "agent", "name": "evaluator", "model": "claude-opus-4-8"}
# The editor that actually performs the code edit (the agent-edit patcher subprocess).
EDITOR = {"type": "agent", "name": "agent-edit", "model": EDITOR_MODEL}

MISSION_META = {
    "name": "agent-edit real-code sprint (concentric circles MLP)",
    "goal": "Maximize test accuracy of a tiny numpy MLP by editing its REAL code (activation + capacity).",
    "objective": {"metric": "accuracy", "direction": "maximize", "target": 0.95},
    "budget": {"max_experiments": 4, "max_runtime_per_experiment_sec": RUN_TIMEOUT_SEC},
    "adapter": "agent_edit_target",
    "patcher": "agent-edit",
    "model": "claude-opus-4-8",
    "editable_files": EDITABLE,
    "allowed_changes": ["activation", "HIDDEN_SIZE", "LEARNING_RATE", "EPOCHS"],
    "constraints": [],
}


# --- helpers ------------------------------------------------------------------
def emit(event_type, payload, **env):
    env.setdefault("mission_id", MISSION_ID)
    return kun_log(event_type, payload, path=OUT_PATH, **env)


def run_target(py_path: str):
    """Execute an (edited) target.py and parse the REAL accuracy from stdout.

    Returns (status, accuracy, runtime_sec, stdout, stderr) where status is one
    of "success" | "nan" | "crash" | "no_metric" | "timeout"."""
    t0 = time.time()
    try:
        proc = subprocess.run(
            [sys.executable, py_path],
            capture_output=True, text=True, timeout=RUN_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired as e:
        return "timeout", None, RUN_TIMEOUT_SEC, e.stdout or "", "timed out"
    rt = round(time.time() - t0, 3)
    if proc.returncode != 0:
        return "crash", None, rt, proc.stdout, proc.stderr
    m = METRIC_RE.search(proc.stdout or "")
    if not m:
        return "no_metric", None, rt, proc.stdout, proc.stderr
    raw = m.group(1).lower()
    if raw == "nan":
        return "nan", float("nan"), rt, proc.stdout, proc.stderr
    return "success", float(raw), rt, proc.stdout, proc.stderr


def baseline_diff(target_py: str) -> str:
    """Real git-style 'new file' diff introducing the baseline target.py."""
    proc = subprocess.run(
        ["git", "diff", "--no-index", "--no-color", "/dev/null", target_py],
        capture_output=True, text=True,
    )  # rc=1 when files differ -- expected
    return proc.stdout


# --- the experiment plan (concrete, single-change proposals) ------------------
PLAN = [
    dict(
        exp_id="exp_001",
        operator="improve",
        hypothesis=("Replace the body of the activation() function so it returns np.tanh(x) "
                    "instead of returning x unchanged."),
        changes={"activation": "np.tanh(x)"},
        rationale=("The baseline uses an identity (linear) activation, so the network collapses to "
                   "a linear classifier and sits near chance on the concentric-circles data. A tanh "
                   "nonlinearity lets the hidden layer carve a curved decision boundary."),
        expected_outcome="Test accuracy rises well above chance (~0.43).",
        risk="tanh saturation could slow convergence at this learning rate.",
    ),
    dict(
        exp_id="exp_002",
        operator="improve",
        hypothesis="Increase model capacity by setting the HIDDEN_SIZE constant from 3 to 8.",
        changes={"HIDDEN_SIZE": 8},
        rationale=("With a working nonlinearity, the 3-unit hidden layer is the bottleneck. A wider "
                   "hidden layer can represent the ring boundary more faithfully."),
        expected_outcome="Test accuracy improves over the tanh/H=3 node.",
        risk="More parameters at fixed epochs could underfit if learning is too slow.",
    ),
    dict(
        exp_id="exp_003",
        operator="improve",
        hypothesis="Further widen the hidden layer by setting HIDDEN_SIZE from 8 to 16.",
        changes={"HIDDEN_SIZE": 16},
        rationale="Push capacity further to see whether the boundary tightens and accuracy climbs again.",
        expected_outcome="Test accuracy improves over the H=8 node and becomes the best run.",
        risk="Diminishing returns or mild overfitting at fixed epochs.",
    ),
]


def main():
    # Fresh output file each run (kun_log appends).
    if os.path.exists(OUT_PATH):
        os.remove(OUT_PATH)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)

    runs_root = tempfile.mkdtemp(prefix="kun_agent_edit_")
    print(f"editor model     : {EDITOR_MODEL}")
    print(f"runs (sandboxes) : {runs_root}")
    print(f"events out       : {OUT_PATH}\n")

    emit("mission_created", MISSION_META)
    emit("mission_started", {"mode": "live", "started_by": "record_agent_edit_run.py"})

    total_cost = 0.0
    best_exp, best_acc = None, float("-inf")
    parent = None
    branch = "branch_main"

    # ---- exp_000 : baseline (run the ORIGINAL target as-is; no agent edit) ----
    base_run = os.path.join(runs_root, "exp_000")
    os.makedirs(base_run, exist_ok=True)
    base_target = os.path.join(base_run, "target.py")
    shutil.copy2(os.path.join(TARGET_DIR, "target.py"), base_target)

    emit("experiment_proposed",
         {"operator": "draft",
          "hypothesis": "Establish the baseline: a 1-hidden-layer numpy MLP with an identity "
                        "(linear) activation and HIDDEN_SIZE=3 on the concentric-circles task.",
          "changes": {"activation": "x (identity)", "HIDDEN_SIZE": 3},
          "expected_outcome": "Near-chance accuracy (linear model cannot separate the rings).",
          "risk": "None; this is the reference point.",
          "rationale": "Baseline reference for all subsequent edits."},
         experiment_id="exp_000", branch_id=branch, parent_experiment_id=None, actor=PLANNER)
    emit("file_diff_created",
         {"file_path": "target.py", "base_file_path": "/dev/null",
          "diff": baseline_diff(base_target)},
         experiment_id="exp_000", branch_id=branch)
    emit("experiment_started",
         {"command": "python target.py", "workspace_path": base_run, "timeout_sec": RUN_TIMEOUT_SEC},
         experiment_id="exp_000", branch_id=branch, parent_experiment_id=None)

    status, acc, rt, out, err = run_target(base_target)
    print(f"exp_000 baseline : status={status} accuracy={acc} ({rt}s)")
    emit("metric_logged", {"name": "accuracy", "value": acc, "step": 1, "phase": "test"},
         experiment_id="exp_000", branch_id=branch)
    emit("experiment_finished",
         {"status": "success", "final_metrics": {"accuracy": acc, "runtime_sec": rt}},
         experiment_id="exp_000", branch_id=branch)
    best_exp, best_acc = "exp_000", acc
    emit("evaluation_created",
         {"verdict": "promote",
          "summary": f"Baseline established at accuracy {acc:.4f} (linear model near chance, as expected).",
          "evidence": [f"identity activation -> {acc:.4f}", "concentric circles are not linearly separable"]},
         experiment_id="exp_000", branch_id=branch, actor=EVALUATOR)
    emit("decision_created",
         {"decision": "promote", "rationale": "Baseline set; introduce a nonlinearity next.",
          "next_action": {"type": "propose_next_experiment", "parent_experiment_id": "exp_000"}},
         experiment_id="exp_000", branch_id=branch)
    parent = "exp_000"

    # ---- exp_001..003 : REAL agent edits, accumulating ----
    source_dir = TARGET_DIR
    for spec in PLAN:
        exp_id = spec["exp_id"]
        workspace = os.path.join(runs_root, exp_id)
        proposal = SimpleNamespace(
            operator=spec["operator"], hypothesis=spec["hypothesis"],
            changes=spec["changes"], rationale=spec["rationale"],
            expected_outcome=spec["expected_outcome"], risk=spec["risk"],
        )

        emit("experiment_proposed",
             {"operator": spec["operator"], "hypothesis": spec["hypothesis"],
              "changes": spec["changes"], "expected_outcome": spec["expected_outcome"],
              "risk": spec["risk"], "rationale": spec["rationale"]},
             experiment_id=exp_id, branch_id=branch, parent_experiment_id=parent, actor=PLANNER)

        # ---- drive the REAL patcher (Claude headless edits the real code) ----
        print(f"{exp_id} editing  : {spec['changes']}  (source={os.path.basename(source_dir)})")
        result = agent_edit.apply(
            workspace=workspace, proposal=proposal, constraints=[],
            editable_files=EDITABLE, model=EDITOR_MODEL, source_dir=source_dir,
        )
        if result.cost_usd:
            total_cost += result.cost_usd

        emit("file_diff_created",
             {"file_path": "target.py", "diff": result.diff or "",
              "commit_sha": result.commit_sha, "session_id": result.session_id,
              "cost_usd": result.cost_usd},
             experiment_id=exp_id, branch_id=branch, actor=EDITOR)

        if not result.ok:
            # Honest failure: the editor produced no valid edit. Record as buggy.
            print(f"{exp_id} EDIT FAIL: {result.error}")
            emit("experiment_started",
                 {"command": "python target.py", "workspace_path": workspace,
                  "timeout_sec": RUN_TIMEOUT_SEC},
                 experiment_id=exp_id, branch_id=branch, parent_experiment_id=parent)
            emit("experiment_failed",
                 {"failure_type": "edit_failed", "message": result.error or "agent-edit failed",
                  "last_metrics": {}},
                 experiment_id=exp_id, branch_id=branch)
            emit("evaluation_created",
                 {"verdict": "reject",
                  "summary": f"agent-edit did not produce a valid edit: {result.error}",
                  "evidence": [result.error or "no diff"]},
                 experiment_id=exp_id, branch_id=branch, actor=EVALUATOR)
            emit("decision_created",
                 {"decision": "retry_debug",
                  "rationale": "Editor flaked; keep the previous best as the parent.",
                  "next_action": {"type": "propose_next_experiment", "parent_experiment_id": parent}},
                 experiment_id=exp_id, branch_id=branch)
            continue  # do NOT accumulate a failed edit; keep source_dir/parent as-is

        # ---- copy the edited target out of the sandbox and RUN it for real ----
        run_dir = os.path.join(runs_root, exp_id + "_run")
        os.makedirs(run_dir, exist_ok=True)
        run_target_py = os.path.join(run_dir, "target.py")
        shutil.copy2(os.path.join(workspace, "target.py"), run_target_py)

        emit("experiment_started",
             {"command": "python target.py", "workspace_path": workspace, "timeout_sec": RUN_TIMEOUT_SEC},
             experiment_id=exp_id, branch_id=branch, parent_experiment_id=parent)

        status, acc, rt, out, err = run_target(run_target_py)
        print(f"{exp_id} result   : status={status} accuracy={acc} ({rt}s)")

        if status != "success":
            # Edited code crashed / NaN'd / produced no metric -> honest failure.
            ftype = {"nan": "nan_detected"}.get(status, status)
            emit("metric_logged", {"name": "accuracy", "value": acc, "step": 1, "phase": "test"},
                 experiment_id=exp_id, branch_id=branch)
            emit("experiment_failed",
                 {"failure_type": ftype,
                  "message": f"edited target.py {status}: {(err or out or '').strip()[:200]}",
                  "last_metrics": {"accuracy": acc}},
                 experiment_id=exp_id, branch_id=branch)
            emit("evaluation_created",
                 {"verdict": "reject",
                  "summary": f"{exp_id} failed at runtime ({status}); recorded as-is.",
                  "evidence": [f"status={status}"]},
                 experiment_id=exp_id, branch_id=branch, actor=EVALUATOR)
            emit("decision_created",
                 {"decision": "retry_debug",
                  "rationale": "Run failed; continue from the last good node.",
                  "next_action": {"type": "propose_next_experiment", "parent_experiment_id": parent}},
                 experiment_id=exp_id, branch_id=branch)
            continue

        emit("metric_logged", {"name": "accuracy", "value": acc, "step": 1, "phase": "test"},
             experiment_id=exp_id, branch_id=branch)
        emit("experiment_finished",
             {"status": "success", "final_metrics": {"accuracy": acc, "runtime_sec": rt}},
             experiment_id=exp_id, branch_id=branch)

        improved = acc > best_acc
        delta = acc - best_acc
        if improved:
            verdict, decision = "promote", "promote"
            summary = f"{exp_id} improved accuracy {best_acc:.4f} -> {acc:.4f} ({delta:+.4f})."
        else:
            verdict, decision = "reject", "reject"
            summary = f"{exp_id} did not beat the best ({acc:.4f} vs {best_acc:.4f}, {delta:+.4f})."
        emit("evaluation_created",
             {"verdict": verdict, "summary": summary,
              "evidence": [f"accuracy {acc:.4f}", f"delta vs best {delta:+.4f}",
                           f"real edit: {result.files_changed}"]},
             experiment_id=exp_id, branch_id=branch, actor=EVALUATOR)
        emit("decision_created",
             {"decision": decision, "rationale": summary,
              "next_action": {"type": "propose_next_experiment", "parent_experiment_id": exp_id}},
             experiment_id=exp_id, branch_id=branch)

        if improved:
            best_exp, best_acc = exp_id, acc
            parent = exp_id              # promote -> next experiment builds on this
            source_dir = workspace       # accumulate edits from the promoted sandbox
        # If not improved, keep parent/source_dir at the last promoted node.

    emit("mission_finished",
         {"status": "completed", "reason": "max_experiments_reached",
          "best_experiment_id": best_exp,
          "best_metric": {"name": "accuracy", "value": best_acc}})

    print(f"\nbest node        : {best_exp} (accuracy={best_acc:.4f})")
    print(f"total cost_usd   : ${total_cost:.4f}")
    print(f"wrote events     : {OUT_PATH}")


if __name__ == "__main__":
    main()
