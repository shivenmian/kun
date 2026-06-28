"""Asset A — generator for Kun's rich sample events.jsonl (P0 UI fixture + backup replay).

This is NOT a real training run. It emits a curated, well-shaped tiny-CNN trajectory that
tells the whole Kun thesis on its own, including the HERO closed-constraint loop:
a NaN at high LR -> a `constraint_learned` with a structured `bound` -> the next proposal
visibly respects that bound (rationale references the constraint).

Run:  python scripts/gen_sample_events.py
Out:  examples/replays/sample.events.jsonl   (deterministic; safe to regenerate/commit)

Schema: docs/03-event-schema.md.  Edit the EXPERIMENTS list to reshape the story.
"""
import json
import pathlib

OUT = pathlib.Path(__file__).resolve().parents[1] / "examples" / "replays" / "sample.events.jsonl"
MISSION = "mission_fashion_sample"
PLANNER = {"type": "agent", "name": "planner", "model": "claude-opus-4-8"}
EVALUATOR = {"type": "agent", "name": "evaluator", "model": "claude-opus-4-8"}
HUMAN = {"type": "human", "name": "user"}

_events = []
_seq = 0


def emit(type_, payload, **env):
    global _seq
    _seq += 1
    rec = {
        "schema_version": 1,
        "event_id": f"evt_{_seq:04d}",
        "timestamp": f"2026-06-27T20:{(_seq // 60):02d}:{(_seq % 60):02d}Z",
        "type": type_,
        "mission_id": MISSION,
        "payload": payload,
    }
    rec.update(env)  # experiment_id / branch_id / parent_experiment_id / actor
    _events.append(rec)


def config_diff(parent_id, exp_id, key, old, new):
    return (
        f"--- runs/{parent_id}/config.yaml\n+++ runs/{exp_id}/config.yaml\n"
        f"@@ -1 +1 @@\n-{key}: {old}\n+{key}: {new}\n"
    )


def run_experiment(exp_id, parent, branch, operator, hypothesis, changes, diff,
                   curve, final, verdict, summary, evidence, decision_text, next_parent):
    """Emit the standard happy-path sequence for one valid experiment."""
    emit("experiment_proposed",
         {"operator": operator, "hypothesis": hypothesis, "changes": changes,
          "rationale": summary},
         experiment_id=exp_id, branch_id=branch, parent_experiment_id=parent, actor=PLANNER)
    emit("file_diff_created", {"file_path": f"runs/{exp_id}/config.yaml", "diff": diff},
         experiment_id=exp_id, branch_id=branch)
    emit("experiment_started",
         {"command": f"python examples/tiny_cnn/train.py --config runs/{exp_id}/config.yaml",
          "workspace_path": f"runs/{exp_id}", "timeout_sec": 90},
         experiment_id=exp_id, branch_id=branch, parent_experiment_id=parent)
    for step, acc in enumerate(curve, 1):
        emit("metric_logged",
             {"name": "val_accuracy", "value": acc, "step": step, "epoch": step, "phase": "validation"},
             experiment_id=exp_id, branch_id=branch)
    emit("experiment_finished", {"status": "success", "final_metrics": final},
         experiment_id=exp_id, branch_id=branch)
    emit("evaluation_created",
         {"verdict": verdict, "summary": summary, "evidence": evidence},
         experiment_id=exp_id, branch_id=branch, actor=EVALUATOR)
    emit("decision_created",
         {"decision": "promote" if verdict == "promote" else "reject",
          "rationale": decision_text,
          "next_action": {"type": "propose_next_experiment", "parent_experiment_id": next_parent}},
         experiment_id=exp_id, branch_id=branch)


# --- Mission -----------------------------------------------------------------
emit("mission_created", {
    "name": "Fashion-MNIST CNN Accuracy Sprint",
    "goal": "Improve validation accuracy on Fashion-MNIST.",
    "objective": {"metric": "val_accuracy", "direction": "maximize", "target": 0.92},
    "budget": {"max_experiments": 8, "max_runtime_per_experiment_sec": 90},
    "adapter": "tiny_cnn", "patcher": "config-patch", "model": "claude-opus-4-8",
    "editable_files": ["config.yaml"],
    "allowed_changes": ["learning_rate", "optimizer", "dropout", "scheduler",
                        "weight_decay", "augmentation"],
    "constraints": [],
})
emit("mission_started", {"mode": "live", "started_by": "user"})

# --- Main branch -------------------------------------------------------------
run_experiment("exp_000", None, "branch_main", "draft",
               "Baseline tiny CNN with Adam.", {"learning_rate": 0.01, "optimizer": "adam", "dropout": 0.25},
               config_diff("base", "exp_000", "learning_rate", "—", "0.01"),
               [0.62, 0.79, 0.873], {"val_accuracy": 0.873, "train_accuracy": 0.91, "runtime_sec": 41.0},
               "promote", "Baseline established at 0.873.", ["baseline run"],
               "Baseline set; try a lower LR next.", "exp_000")

run_experiment("exp_001", "exp_000", "branch_main", "improve",
               "Lowering LR should stabilise training.", {"learning_rate": 0.003},
               config_diff("exp_000", "exp_001", "learning_rate", "0.01", "0.003"),
               [0.71, 0.85, 0.889], {"val_accuracy": 0.889, "train_accuracy": 0.92, "runtime_sec": 43.0},
               "promote", "Lower LR improved val_accuracy 0.873 -> 0.889.",
               ["+0.016 over exp_000", "no instability"],
               "LR helped; add cosine scheduling.", "exp_001")

run_experiment("exp_002", "exp_001", "branch_main", "improve",
               "Cosine scheduling should preserve gains with smoother convergence.", {"scheduler": "cosine"},
               config_diff("exp_001", "exp_002", "scheduler", "none", "cosine"),
               [0.78, 0.88, 0.901], {"val_accuracy": 0.901, "train_accuracy": 0.93, "runtime_sec": 44.0},
               "promote", "Cosine scheduling reached 0.901 (best so far).",
               ["+0.012 over exp_001"], "Best so far; probe a more aggressive LR.", "exp_002")

# --- HERO: a failure -> learned constraint -> next proposal respects it -------
# exp_003: aggressive LR -> NaN (buggy)
emit("experiment_proposed",
     {"operator": "improve", "hypothesis": "A higher peak LR may converge faster.",
      "changes": {"learning_rate": 0.02},
      "rationale": "Pushing LR to test the upper bound of stability."},
     experiment_id="exp_003", branch_id="branch_main", parent_experiment_id="exp_002", actor=PLANNER)
emit("file_diff_created",
     {"file_path": "runs/exp_003/config.yaml", "diff": config_diff("exp_002", "exp_003", "learning_rate", "0.003", "0.02")},
     experiment_id="exp_003", branch_id="branch_main")
emit("experiment_started",
     {"command": "python examples/tiny_cnn/train.py --config runs/exp_003/config.yaml",
      "workspace_path": "runs/exp_003", "timeout_sec": 90},
     experiment_id="exp_003", branch_id="branch_main", parent_experiment_id="exp_002")
emit("metric_logged", {"name": "val_accuracy", "value": 0.41, "step": 1, "epoch": 1, "phase": "validation"},
     experiment_id="exp_003", branch_id="branch_main")
emit("experiment_failed",
     {"failure_type": "nan_detected", "message": "Training loss became NaN at epoch 2.",
      "last_metrics": {"train_loss": "nan", "val_accuracy": 0.41}},
     experiment_id="exp_003", branch_id="branch_main")
# the learned constraint, WITH a structured bound (machine-checkable)
emit("constraint_learned",
     {"constraint_id": "learned_001", "source": "learned",
      "text": "learning_rate > 0.01 caused NaNs (exp_003). Ban it.",
      "applies_to": ["learning_rate"],
      "bound": {"param": "learning_rate", "op": ">", "value": 0.01},
      "confidence": "high", "supporting_experiments": ["exp_003"]},
     experiment_id="exp_003", branch_id="branch_main")
emit("evaluation_created",
     {"verdict": "reject", "summary": "Diverged to NaN; LR too high. Learned an upper bound.",
      "evidence": ["NaN at epoch 2", "val_accuracy collapsed to 0.41"]},
     experiment_id="exp_003", branch_id="branch_main", actor=EVALUATOR)
emit("decision_created",
     {"decision": "retry_debug", "rationale": "Back off LR below the learned bound and continue from exp_002.",
      "next_action": {"type": "propose_next_experiment", "parent_experiment_id": "exp_002"}},
     experiment_id="exp_003", branch_id="branch_main")

# exp_004: the next proposal VISIBLY respects the learned bound (the hero payoff)
run_experiment("exp_004", "exp_002", "branch_main", "improve",
               "Stay below the learned LR bound (0.01) while keeping cosine scheduling.",
               {"learning_rate": 0.004},
               config_diff("exp_002", "exp_004", "learning_rate", "0.003", "0.004"),
               [0.80, 0.89, 0.905], {"val_accuracy": 0.905, "train_accuracy": 0.93, "runtime_sec": 44.0},
               "promote",
               "Respecting learned constraint (lr <= 0.01): 0.004 improved to 0.905, no NaNs.",
               ["honors learned_001 (lr <= 0.01)", "+0.004 over exp_002", "stable"],
               "Constraint-guided LR worked; add light augmentation.", "exp_004")

run_experiment("exp_005", "exp_004", "branch_main", "improve",
               "Light augmentation should improve generalisation.", {"augmentation": True},
               config_diff("exp_004", "exp_005", "augmentation", "false", "true"),
               [0.83, 0.90, 0.912], {"val_accuracy": 0.912, "train_accuracy": 0.93, "runtime_sec": 47.0},
               "promote", "Augmentation reached 0.912 (best).", ["+0.007 over exp_004"],
               "New best; try higher dropout.", "exp_005")

run_experiment("exp_006", "exp_005", "branch_main", "improve",
               "Higher dropout may regularise further.", {"dropout": 0.5},
               config_diff("exp_005", "exp_006", "dropout", "0.25", "0.5"),
               [0.79, 0.86, 0.881], {"val_accuracy": 0.881, "train_accuracy": 0.85, "runtime_sec": 47.0},
               "reject", "Dropout 0.5 underfit (0.912 -> 0.881).",
               ["-0.031 vs exp_005", "train_acc dropped -> underfitting"],
               "Reject; dropout too high.", "exp_005")
emit("constraint_learned",
     {"constraint_id": "learned_002", "source": "learned",
      "text": "dropout > 0.4 underfits the tiny CNN.",
      "applies_to": ["dropout"], "bound": {"param": "dropout", "op": ">", "value": 0.4},
      "confidence": "medium", "supporting_experiments": ["exp_006"]},
     experiment_id="exp_006", branch_id="branch_main")

# --- Human fork from the best node, with a constraint ------------------------
emit("fork_created",
     {"instruction": "Fork from the best run; keep augmentation, ban dropout > 0.4, try weight decay.",
      "reason": "exp_005 is best; explore regularisation without underfitting."},
     branch_id="branch_human_001", parent_experiment_id="exp_005", actor=HUMAN)
emit("branch_created",
     {"name": "human-fork-weight-decay", "source": "human_fork",
      "reason": "Forked from best node (exp_005) to test weight decay under the dropout bound."},
     branch_id="branch_human_001", parent_experiment_id="exp_005")
emit("constraint_added",
     {"constraint_id": "human_001", "source": "human",
      "text": "Ban dropout > 0.4 (underfits).", "applies_to": ["dropout"],
      "bound": {"param": "dropout", "op": ">", "value": 0.4}},
     branch_id="branch_human_001", actor=HUMAN)

run_experiment("exp_007", "exp_005", "branch_human_001", "improve",
               "Add weight decay for regularisation without raising dropout.", {"weight_decay": 0.0005},
               config_diff("exp_005", "exp_007", "weight_decay", "0.0", "0.0005"),
               [0.84, 0.905, 0.915], {"val_accuracy": 0.915, "train_accuracy": 0.93, "runtime_sec": 47.0},
               "promote", "Weight decay reached 0.915 (new best), dropout within bound.",
               ["+0.003 over exp_005", "honors human_001"],
               "New best on the human fork.", "exp_007")

emit("mission_finished",
     {"status": "completed", "reason": "max_experiments_reached",
      "best_experiment_id": "exp_007", "best_metric": {"name": "val_accuracy", "value": 0.915}})

# --- write -------------------------------------------------------------------
OUT.parent.mkdir(parents=True, exist_ok=True)
with open(OUT, "w") as f:
    for e in _events:
        f.write(json.dumps(e) + "\n")
print(f"wrote {len(_events)} events -> {OUT}")
