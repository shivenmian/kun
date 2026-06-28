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
  "schema_version": 1,
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
schema_version
event_id
timestamp
type
mission_id
payload
```

`schema_version` is an integer on every event (append-only logs are forever; this is cheap insurance for future migrations). MVP = `1`.

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
    ],
    "constraints": []
  }
}
```

Initial constraints may be seeded here (empty for a fresh mission) or emitted as `constraint_added` events at mission start. See the canonical constraint object under `constraint_added`/`constraint_learned`.

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

Human-specified or learned constraint. `constraint_added` and `constraint_learned` share **one canonical object** that the research-memory panel renders: `constraint_id`, `source` (`human`|`learned`), `text`, `applies_to`, optional structured `bound` (`{param, op, value}`), and (for learned) `confidence` + `supporting_experiments`. The **`bound` is what the planner hard-rejects against** to make the closed constraint loop deterministic (spec §4) — always include it when the constraint is a numeric limit.

```json
{
  "type": "constraint_added",
  "mission_id": "mission_fashion_001",
  "branch_id": "branch_cosine_lr",
  "payload": {
    "constraint_id": "constraint_001",
    "source": "human",
    "text": "Avoid learning_rate > 0.003 because prior runs became unstable.",
    "applies_to": ["learning_rate"],
    "bound": {"param": "learning_rate", "op": ">", "value": 0.003}
  }
}
```

### experiment_proposed

Emitted before any patch/run.

`operator` (required) is the AIDE-style proposal type: `draft` (new approach from scratch) | `debug` (repair a `buggy` parent, preserving its approach) | `improve` (exactly one atomic change to a `valid` parent, so the metric delta is attributable). The UI badges nodes by operator.

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
    "operator": "improve",
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

When the diff was produced by the **agent-edit** patcher (P1), the payload MAY also carry optional
telemetry — `commit_sha`, `session_id`, `cost_usd` — and an `actor` of
`{"type":"agent","name":"agent-edit","model":"<editor-model>"}`. These are additive/optional; the
state builder ignores unknown fields (config-patch omits them).

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

`decision` ∈ `{continue_branch, promote, reject, retry_debug, fork, stop}`. Each selection-policy branch (spec §4) emits one so the graph shows *why* each node was expanded.

### constraint_learned

```json
{
  "type": "constraint_learned",
  "mission_id": "mission_fashion_001",
  "experiment_id": "exp_005",
  "payload": {
    "constraint_id": "learned_002",
    "source": "learned",
    "text": "learning_rate > 0.004 caused unstable training in 2 experiments.",
    "confidence": "medium",
    "supporting_experiments": ["exp_002", "exp_005"],
    "applies_to": ["learning_rate"],
    "bound": {"param": "learning_rate", "op": ">", "value": 0.004}
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

### Human steering events (v4) — P1, live

**Status: built in P1.** Emitted by the cockpit (via the §5.1 endpoints `POST .../instruct`,
`.../experiments/{id}/approve`, `.../experiments/{id}/reject`) when a human steers a live
(Mode A) mission; the API appends them through `kun_log` like any event. The Mode-A loop reads
them back from its own log; in Mode B, the external loop reads them via `GET /missions/{id}/state`
(the feedback channel) and obeys. See CONTRACT §9 for the full loop interface.

**Stop / pause is NOT an event** — it is imperative loop state set via `POST /missions/{id}/stop`
through the control file `runs/<id>/control.json` (CONTRACT §9.2). A `stop` ultimately surfaces as
`mission_finished{reason:"user_stop"}` (the existing event below); `pause`/`resume` flip run-state
without emitting an event.

```json
{"type": "instruction_added", "mission_id": "mission_fashion_001", "branch_id": "branch_main",
 "actor": {"type": "human", "name": "user"},
 "payload": {"instruction_id": "instr_001", "text": "Try cosine scheduling next; we're plateauing.",
             "applies_from": "exp_006"}}
```

```json
{"type": "experiment_approved", "mission_id": "mission_fashion_001", "experiment_id": "exp_007",
 "actor": {"type": "human", "name": "user"},
 "payload": {"edited": false, "note": "Looks good, run it."}}
```

```json
{"type": "experiment_rejected", "mission_id": "mission_fashion_001", "experiment_id": "exp_007",
 "actor": {"type": "human", "name": "user"},
 "payload": {"reason": "dropout too high; will underfit", "replacement_changes": {"dropout": 0.2}}}
```

The **approval gate** holds a `proposed` experiment until an `experiment_approved` (optionally with `edited: true` + the human's `changes`) or `experiment_rejected` arrives. `instruction_added` biases the next proposal (and, with a structured `bound` in its payload, can hard-reject like a constraint).

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
  operator?: "draft" | "debug" | "improve";
  status: "proposed" | "running" | "valid" | "buggy" | "promoted" | "rejected" | "forked";
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

Status mapping from outcome events: `experiment_finished` (status `success`) → derived node status `valid`; `experiment_failed` → `buggy` (the `debug` operator targets these). The raw event payloads keep their `success`/`failed`/`nan_detected` wording; `valid`/`buggy` is the node-lifecycle vocabulary the cockpit renders.

## MVP acceptance criteria

The schema is good enough if it can represent:

- tiny CNN live experiments
- at least one failed experiment
- one promoted branch
- one learned constraint
- one human fork
- modded-nanogpt replay with diffs, metrics, rationale, and throughput/runtime information
