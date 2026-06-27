# Kun Event Schema

## Purpose

The event log is Kun's flight recorder. Every important action in a research mission should be captured as an append-only JSONL event.

The event log must support:

- live UI updates
- replay from saved sessions
- debugging failed missions
- importing/converting external runs
- reconstructing the full research trajectory
- forking from previous experiments

## Principles

1. **Append-only**
   - Do not mutate old events.
   - Corrections should be new events.

2. **Replayable**
   - The UI should be reconstructable from events alone.

3. **Human-readable payloads**
   - Events should include enough textual context to make demos and debugging easy.

4. **Structured enough for UI**
   - Avoid putting everything in opaque log text.

5. **Adapter-friendly**
   - Events should work for tiny CNN, modded-nanogpt, future eval loops, and future finetuning loops.

## Base event envelope

Every event should use this envelope:

```json
{
  "event_id": "evt_000123",
  "timestamp": "2026-06-27T20:15:42.123Z",
  "type": "experiment_started",
  "mission_id": "mission_abc",
  "experiment_id": "exp_004",
  "branch_id": "branch_main",
  "parent_experiment_id": "exp_003",
  "payload": {}
}
```

Required fields:

```text
event_id
timestamp
type
mission_id
payload
```

Optional fields:

```text
experiment_id
branch_id
parent_experiment_id
actor
```

Recommended actor field:

```json
"actor": {
  "type": "agent",
  "name": "planner",
  "model": "gpt-5.5"
}
```

or:

```json
"actor": {
  "type": "human",
  "name": "user"
}
```

## Core event types

### mission_created

Emitted when a mission is created.

```json
{
  "type": "mission_created",
  "mission_id": "mission_fashion_001",
  "payload": {
    "name": "Fashion-MNIST CNN Accuracy Sprint",
    "goal": "Improve validation accuracy on Fashion-MNIST.",
    "objective": {
      "metric": "val_accuracy",
      "direction": "maximize",
      "target": 0.92
    },
    "budget": {
      "max_experiments": 6,
      "max_runtime_per_experiment_sec": 90
    },
    "adapter": "tiny_cnn",
    "editable_files": ["config.yaml"],
    "allowed_changes": [
      "learning_rate",
      "optimizer",
      "dropout",
      "batch_size",
      "conv_channels",
      "weight_decay",
      "augmentation",
      "scheduler"
    ]
  }
}
```

### mission_started

```json
{
  "type": "mission_started",
  "mission_id": "mission_fashion_001",
  "payload": {
    "mode": "live",
    "started_by": "user"
  }
}
```

### branch_created

```json
{
  "type": "branch_created",
  "mission_id": "mission_fashion_001",
  "branch_id": "branch_cosine_lr",
  "parent_experiment_id": "exp_003",
  "payload": {
    "name": "cosine-lr-fork",
    "reason": "Forked from the best scheduler run to test a safer learning-rate range.",
    "source": "human_fork"
  }
}
```

### constraint_added

Human-specified or learned constraint.

```json
{
  "type": "constraint_added",
  "mission_id": "mission_fashion_001",
  "branch_id": "branch_cosine_lr",
  "payload": {
    "constraint_id": "constraint_001",
    "source": "human",
    "text": "Avoid learning_rate > 0.003 because prior runs became unstable.",
    "applies_to": ["learning_rate"]
  }
}
```

### experiment_proposed

Emitted before any patch/run.

```json
{
  "type": "experiment_proposed",
  "mission_id": "mission_fashion_001",
  "experiment_id": "exp_004",
  "branch_id": "branch_cosine_lr",
  "parent_experiment_id": "exp_003",
  "actor": {
    "type": "agent",
    "name": "planner",
    "model": "gpt-5.5"
  },
  "payload": {
    "hypothesis": "Lowering the learning rate while keeping cosine scheduling should retain the previous convergence gains with less instability.",
    "changes": {
      "learning_rate": 0.0015,
      "scheduler": "cosine",
      "dropout": 0.25,
      "batch_size": 128
    },
    "expected_outcome": "Validation accuracy should improve without oscillation.",
    "risk": "A lower LR may slow early convergence.",
    "rationale": "Previous experiment improved validation accuracy with cosine scheduling, but a high LR caused unstable loss."
  }
}
```

### file_diff_created

```json
{
  "type": "file_diff_created",
  "mission_id": "mission_fashion_001",
  "experiment_id": "exp_004",
  "branch_id": "branch_cosine_lr",
  "payload": {
    "file_path": "runs/exp_004/config.yaml",
    "base_file_path": "runs/exp_003/config.yaml",
    "diff": "--- exp_003/config.yaml\n+++ exp_004/config.yaml\n@@ -1,5 +1,5 @@\n-learning_rate: 0.003\n+learning_rate: 0.0015\n scheduler: cosine\n dropout: 0.25\n batch_size: 128\n"
  }
}
```

### experiment_started

```json
{
  "type": "experiment_started",
  "mission_id": "mission_fashion_001",
  "experiment_id": "exp_004",
  "branch_id": "branch_cosine_lr",
  "parent_experiment_id": "exp_003",
  "payload": {
    "command": "python examples/tiny_cnn/train.py --config runs/exp_004/config.yaml",
    "workspace_path": "runs/exp_004",
    "timeout_sec": 90
  }
}
```

### command_output

Optional; useful for visible live logs. Keep concise or reference log files.

```json
{
  "type": "command_output",
  "mission_id": "mission_fashion_001",
  "experiment_id": "exp_004",
  "payload": {
    "stream": "stdout",
    "text": "epoch=1 train_loss=0.512 val_accuracy=0.851\n"
  }
}
```

### metric_logged

```json
{
  "type": "metric_logged",
  "mission_id": "mission_fashion_001",
  "experiment_id": "exp_004",
  "branch_id": "branch_cosine_lr",
  "payload": {
    "name": "val_accuracy",
    "value": 0.881,
    "step": 1,
    "epoch": 1,
    "phase": "validation"
  }
}
```

Additional metrics:

```json
{
  "type": "metric_logged",
  "mission_id": "mission_fashion_001",
  "experiment_id": "exp_004",
  "payload": {
    "name": "runtime_sec",
    "value": 42.8,
    "step": 0
  }
}
```

### experiment_finished

```json
{
  "type": "experiment_finished",
  "mission_id": "mission_fashion_001",
  "experiment_id": "exp_004",
  "branch_id": "branch_cosine_lr",
  "payload": {
    "status": "success",
    "final_metrics": {
      "val_accuracy": 0.902,
      "train_accuracy": 0.936,
      "runtime_sec": 67.4
    },
    "artifacts": [
      {
        "type": "metrics_jsonl",
        "path": "runs/exp_004/metrics.jsonl"
      },
      {
        "type": "stdout",
        "path": "runs/exp_004/stdout.log"
      }
    ]
  }
}
```

### experiment_failed

```json
{
  "type": "experiment_failed",
  "mission_id": "mission_fashion_001",
  "experiment_id": "exp_005",
  "branch_id": "branch_main",
  "payload": {
    "failure_type": "nan_detected",
    "message": "Training loss became NaN at epoch 2.",
    "last_metrics": {
      "train_loss": "nan",
      "val_accuracy": 0.721
    },
    "stdout_path": "runs/exp_005/stdout.log",
    "stderr_path": "runs/exp_005/stderr.log"
  }
}
```

### evaluation_created

```json
{
  "type": "evaluation_created",
  "mission_id": "mission_fashion_001",
  "experiment_id": "exp_004",
  "branch_id": "branch_cosine_lr",
  "actor": {
    "type": "agent",
    "name": "evaluator",
    "model": "gpt-5.5"
  },
  "payload": {
    "verdict": "promote",
    "summary": "The experiment improved validation accuracy from 0.889 to 0.902 while remaining within the runtime budget.",
    "evidence": [
      "val_accuracy improved by 0.013 over parent exp_003",
      "runtime stayed under 90 seconds",
      "train/val gap did not increase significantly"
    ],
    "concerns": [
      "Only one seed has been tested"
    ]
  }
}
```

### decision_created

```json
{
  "type": "decision_created",
  "mission_id": "mission_fashion_001",
  "experiment_id": "exp_004",
  "branch_id": "branch_cosine_lr",
  "payload": {
    "decision": "continue_branch",
    "rationale": "Cosine scheduling with lower LR improved validation accuracy. Next, test whether mild augmentation improves generalization.",
    "next_action": {
      "type": "propose_next_experiment",
      "parent_experiment_id": "exp_004"
    }
  }
}
```

### constraint_learned

```json
{
  "type": "constraint_learned",
  "mission_id": "mission_fashion_001",
  "experiment_id": "exp_005",
  "payload": {
    "constraint_id": "learned_002",
    "text": "learning_rate > 0.004 caused unstable training in 2 experiments.",
    "confidence": "medium",
    "supporting_experiments": ["exp_002", "exp_005"],
    "applies_to": ["learning_rate"]
  }
}
```

### fork_created

```json
{
  "type": "fork_created",
  "mission_id": "mission_fashion_001",
  "branch_id": "branch_human_001",
  "parent_experiment_id": "exp_004",
  "actor": {
    "type": "human",
    "name": "user"
  },
  "payload": {
    "instruction": "Fork from this run, keep cosine scheduler, and avoid learning_rate > 0.003.",
    "reason": "The selected node had the best validation accuracy, but nearby high-LR experiments were unstable."
  }
}
```

### mission_finished

```json
{
  "type": "mission_finished",
  "mission_id": "mission_fashion_001",
  "payload": {
    "status": "completed",
    "reason": "max_experiments_reached",
    "best_experiment_id": "exp_004",
    "best_metric": {
      "name": "val_accuracy",
      "value": 0.902
    }
  }
}
```

## Replay requirements

A replay file is a plain JSONL file:

```text
one JSON event per line
sorted by timestamp/event order
self-contained enough to rebuild state
```

Replay mode should:

1. Load all events.
2. Reconstruct mission state.
3. Allow selecting nodes and viewing metrics/diffs/rationales.
4. Optionally support playback timing later.

For MVP, instant load is enough; a timeline scrubber is nice-to-have.

## Materialized experiment state

The UI can derive this experiment model:

```ts
type Experiment = {
  id: string;
  parentId?: string;
  branchId: string;
  status: "proposed" | "running" | "success" | "failed" | "promoted" | "rejected" | "forked";
  hypothesis?: string;
  rationale?: string;
  changes?: Record<string, unknown>;
  diff?: string;
  command?: string;
  metrics: MetricPoint[];
  finalMetrics?: Record<string, number>;
  verdict?: string;
  evidence?: string[];
  concerns?: string[];
};
```

## MVP acceptance criteria

The schema is good enough if it can represent:

- tiny CNN live experiments
- at least one failed experiment
- one promoted branch
- one learned constraint
- one human fork
- modded-nanogpt replay with diffs, metrics, rationale, and throughput/runtime information
