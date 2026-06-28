"""Asset B converter (Mode-B fallback) — nanogpt run artifacts -> Kun events.jsonl.

The serious run itself is real compute (doc 07). This script turns its artifacts into a
schema-valid Kun trajectory. Two ways to use it:

  1. RECOMMENDED when artifacts are messy (doc 07 says so): fill the ATTEMPTS list at the
     bottom with the REAL numbers from your run, then:
         python scripts/convert_nanogpt.py -o examples/replays/nanogpt.events.jsonl
  2. Auto-parse a run dir: wire parse_run_dir() to your real artifact format, then:
         python scripts/convert_nanogpt.py --run-dir runs/nanogpt_overnight -o <out>

HONESTY GUARD (doc 07/08): output must reflect what actually happened. The shipped ATTEMPTS
are a tiny PLACEHOLDER so the script runs end-to-end; replace them with real data and never
present placeholder numbers as a real run. The script prints a loud warning if it emits the
placeholder.

Schema: docs/03-event-schema.md.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
from dataclasses import dataclass, field

PLANNER = {"type": "agent", "name": "planner", "model": "claude-opus-4-8"}
EVALUATOR = {"type": "agent", "name": "evaluator", "model": "claude-opus-4-8"}

MISSION_META = {
    "mission_id": "modded_nanogpt_run",
    "name": "modded-nanogpt optimization (recorded)",
    "goal": "Reduce steps/time to target validation loss.",
    "objective": {"metric": "val_loss", "direction": "minimize", "target": 3.28},
    "budget": {"max_experiments": 12, "max_runtime_per_experiment_sec": 1800},
    "adapter": "modded_nanogpt",
    "patcher": "agent-edit",  # preferred (Kun-driven). Use "config-patch"/external for Mode-B ingest.
    "model": "claude-opus-4-8",
    "editable_files": ["train_gpt.py"],
    "constraints": [],
}


@dataclass
class Attempt:
    """One nanogpt experiment, filled from REAL run data."""
    exp_id: str
    parent: str | None
    hypothesis: str
    changes: dict                                  # {"optimizer": "muon", ...} — what changed
    diff: str                                      # real unified diff of train_gpt.py
    metrics: list[tuple[str, float, int]]          # [(name, value, step), ...] real time series
    status: str                                    # "valid" | "buggy"
    final_metrics: dict | None = None              # {"val_loss":.., "runtime_sec":.., "tokens_per_sec":..}
    failure: dict | None = None                    # buggy: {"failure_type","message","last_metrics"}
    verdict: str = "promote"                       # "promote" | "reject"
    summary: str = ""
    evidence: list[str] = field(default_factory=list)
    command: str = "torchrun --nproc_per_node=8 train_gpt.py"
    operator: str | None = None                    # inferred if None (draft/debug/improve)
    branch: str = "branch_main"
    timestamp: str | None = None                   # real ISO-8601 ts if available


# --- emit --------------------------------------------------------------------
def build_events(meta: dict, attempts: list[Attempt]) -> list[dict]:
    mission_id = meta["mission_id"]
    by_id = {a.exp_id: a for a in attempts}
    events: list[dict] = []
    seq = 0

    def emit(type_, payload, ts=None, **env):
        nonlocal seq
        seq += 1
        rec = {
            "schema_version": 1,
            "event_id": f"evt_{seq:04d}",
            "timestamp": ts or f"2026-06-27T20:{(seq // 60):02d}:{(seq % 60):02d}Z",
            "type": type_,
            "mission_id": mission_id,
            "payload": payload,
        }
        rec.update(env)
        events.append(rec)

    def infer_operator(a: Attempt) -> str:
        if a.operator:
            return a.operator
        if a.parent is None:
            return "draft"
        p = by_id.get(a.parent)
        return "debug" if (p and p.status == "buggy") else "improve"

    emit("mission_created", {k: v for k, v in meta.items() if k != "mission_id"})
    emit("mission_started", {"mode": "replay", "started_by": "converter"})

    for a in attempts:
        op = infer_operator(a)
        emit("experiment_proposed",
             {"operator": op, "hypothesis": a.hypothesis, "changes": a.changes,
              "rationale": a.summary or a.hypothesis},
             ts=a.timestamp, experiment_id=a.exp_id, branch_id=a.branch,
             parent_experiment_id=a.parent, actor=PLANNER)
        emit("file_diff_created", {"file_path": "train_gpt.py", "diff": a.diff},
             ts=a.timestamp, experiment_id=a.exp_id, branch_id=a.branch)
        emit("experiment_started",
             {"command": a.command, "workspace_path": f"runs/nanogpt/{a.exp_id}", "timeout_sec": 1800},
             ts=a.timestamp, experiment_id=a.exp_id, branch_id=a.branch, parent_experiment_id=a.parent)
        for name, value, step in a.metrics:
            emit("metric_logged", {"name": name, "value": value, "step": step},
                 ts=a.timestamp, experiment_id=a.exp_id, branch_id=a.branch)

        if a.status == "valid":
            emit("experiment_finished", {"status": "success", "final_metrics": a.final_metrics or {}},
                 ts=a.timestamp, experiment_id=a.exp_id, branch_id=a.branch)
        else:
            emit("experiment_failed", a.failure or {"failure_type": "error", "message": "run failed"},
                 ts=a.timestamp, experiment_id=a.exp_id, branch_id=a.branch)
            # NaN on a numeric change -> a learned constraint with a machine-checkable bound
            learned = _bound_from_nan(a)
            if learned:
                emit("constraint_learned", learned, ts=a.timestamp,
                     experiment_id=a.exp_id, branch_id=a.branch)

        emit("evaluation_created",
             {"verdict": a.verdict, "summary": a.summary, "evidence": a.evidence},
             ts=a.timestamp, experiment_id=a.exp_id, branch_id=a.branch, actor=EVALUATOR)
        emit("decision_created",
             {"decision": "promote" if a.verdict == "promote" else "reject",
              "rationale": a.summary,
              "next_action": {"type": "propose_next_experiment", "parent_experiment_id": a.exp_id}},
             ts=a.timestamp, experiment_id=a.exp_id, branch_id=a.branch)

    # mission_finished: best = lowest val_loss among valid attempts
    valid = [a for a in attempts if a.status == "valid" and (a.final_metrics or {}).get("val_loss") is not None]
    best = min(valid, key=lambda a: a.final_metrics["val_loss"], default=None)
    emit("mission_finished",
         {"status": "completed", "reason": "max_experiments_reached",
          "best_experiment_id": best.exp_id if best else None,
          "best_metric": {"name": "val_loss", "value": best.final_metrics["val_loss"]} if best else None})
    return events


def _bound_from_nan(a: Attempt) -> dict | None:
    """If a run NaN'd after raising a numeric param, learn an upper-bound constraint."""
    ft = (a.failure or {}).get("failure_type", "")
    if "nan" not in ft.lower():
        return None
    numeric = {k: v for k, v in a.changes.items() if isinstance(v, (int, float))}
    if not numeric:
        return None
    param, value = next(iter(numeric.items()))
    return {
        "constraint_id": f"learned_{a.exp_id}",
        "source": "learned",
        "text": f"{param} = {value} caused {ft} in {a.exp_id}; treat as an upper bound.",
        "applies_to": [param],
        "bound": {"param": param, "op": ">", "value": value},
        "confidence": "high",
        "supporting_experiments": [a.exp_id],
    }


# --- artifact parsing (wire this to your real run) ---------------------------
_METRIC_RE = re.compile(r"step[=:\s]+(\d+).*?val[_ ]loss[=:\s]+([0-9.]+)", re.I)


def parse_metric_lines(text: str) -> list[tuple[str, float, int]]:
    """Helper: pull (val_loss, step) points out of a training log. Adjust the regex to your format."""
    out = []
    for m in _METRIC_RE.finditer(text):
        out.append(("val_loss", float(m.group(2)), int(m.group(1))))
    return out


def parse_run_dir(run_dir: pathlib.Path) -> list[Attempt]:
    """TODO: map your real artifacts -> [Attempt].

    auto-nanogpt / Claude-Code runs typically leave: a markdown harness (e.g. scratchpad/THREAD.md),
    git history (one commit per attempt -> `git show` for the diff), and per-attempt training logs.
    Suggested shape:
      - one Attempt per attempt/commit; diff = `git show <sha> -- train_gpt.py`
      - metrics via parse_metric_lines(open(log).read())
      - status = "buggy" if the log contains NaN/crash else "valid"
      - hypothesis/summary from the THREAD.md entry for that attempt
    Until wired, raise so nobody ships empty output by accident.
    """
    raise NotImplementedError(
        "parse_run_dir() not wired yet. Either implement it for your artifact format, "
        "or fill the ATTEMPTS list and run without --run-dir (hand-author from real numbers)."
    )


# --- PLACEHOLDER attempts (REPLACE with your real run) -----------------------
# Tiny illustrative trajectory so the script runs end-to-end. NOT real data.
ATTEMPTS: list[Attempt] = [
    Attempt("exp_000", None,
            "Baseline modded-nanogpt config.", {},
            "--- a/train_gpt.py\n+++ b/train_gpt.py\n@@ baseline @@\n",
            [("val_loss", 3.55, 1000), ("val_loss", 3.42, 2000)], "valid",
            final_metrics={"val_loss": 3.42, "runtime_sec": 360, "tokens_per_sec": 121000},
            verdict="promote", summary="Baseline at val_loss 3.42.", evidence=["baseline"]),
    Attempt("exp_001", "exp_000",
            "Swap AdamW for the Muon optimizer on hidden matrices.", {"optimizer": "muon"},
            "--- a/train_gpt.py\n+++ b/train_gpt.py\n@@ optimizer @@\n-optimizer = AdamW(...)\n+optimizer = Muon(...)\n",
            [("val_loss", 3.40, 1000), ("val_loss", 3.31, 2000)], "valid",
            final_metrics={"val_loss": 3.31, "runtime_sec": 352, "tokens_per_sec": 123500},
            verdict="promote", summary="Muon improved val_loss 3.42 -> 3.31.",
            evidence=["-0.11 vs baseline", "throughput ~stable"]),
    Attempt("exp_002", "exp_001",
            "Aggressive peak LR to converge faster.", {"peak_lr": 0.05},
            "--- a/train_gpt.py\n+++ b/train_gpt.py\n@@ lr @@\n-peak_lr = 0.018\n+peak_lr = 0.05\n",
            [("val_loss", 4.10, 500)], "buggy",
            failure={"failure_type": "nan_detected", "message": "loss -> NaN at step ~600",
                     "last_metrics": {"val_loss": 4.10}},
            verdict="reject", summary="Diverged; learned a peak_lr upper bound.",
            evidence=["NaN early"]),
    Attempt("exp_003", "exp_001",
            "Back off peak LR below the learned bound; add warmup.", {"peak_lr": 0.02, "warmup_steps": 300},
            "--- a/train_gpt.py\n+++ b/train_gpt.py\n@@ lr @@\n-peak_lr = 0.018\n+peak_lr = 0.02\n+warmup_steps = 300\n",
            [("val_loss", 3.36, 1000), ("val_loss", 3.27, 2000)], "valid",
            final_metrics={"val_loss": 3.27, "runtime_sec": 349, "tokens_per_sec": 123900},
            verdict="promote", summary="Respecting learned peak_lr bound: best val_loss 3.27, no NaNs.",
            evidence=["honors learned bound", "-0.04 vs exp_001", "crossed target 3.28"]),
]


def main():
    ap = argparse.ArgumentParser(description="Convert a nanogpt run into Kun events.jsonl")
    ap.add_argument("-o", "--out", default="examples/replays/nanogpt.events.jsonl")
    ap.add_argument("--run-dir", help="auto-parse this artifact dir (requires wiring parse_run_dir)")
    args = ap.parse_args()

    if args.run_dir:
        attempts = parse_run_dir(pathlib.Path(args.run_dir))
        placeholder = False
    else:
        attempts = ATTEMPTS
        placeholder = True

    events = build_events(MISSION_META, attempts)
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")
    print(f"wrote {len(events)} events -> {out}")
    if placeholder:
        print("\n  WARNING: used PLACEHOLDER ATTEMPTS (not a real run). Replace ATTEMPTS with your "
              "real run's numbers (or wire --run-dir) before using this in the demo. (doc 07 honesty guard)")


if __name__ == "__main__":
    main()
