# modded-nanogpt Runbook for Kun

## Purpose

The modded-nanogpt path is Kun's serious credibility demo. It should show that Kun is not just a toy CNN dashboard, but a cockpit for real autonomous ML optimization work.

The goal is not necessarily to beat the leaderboard during the hackathon. The goal is to create a rich, inspectable, replayable research trajectory.

## Demo role

Use modded-nanogpt for:

- serious replay
- real ML credibility
- optimizer/scheduler/code-diff examples
- loss curves and throughput metrics
- failures/instability/NaNs
- learned constraints
- fork-from-node visual demonstration

Do not depend on live modded-nanogpt execution during judging.

## Desired mission framing

```text
Mission: modded-nanogpt optimization
Goal: Improve training efficiency toward target validation loss.
Primary objective: minimize steps/time to target validation loss.
Secondary objectives: maintain throughput, avoid instability/NaNs.
Constraints: limited runtime per experiment, reproducible seed if possible.
```

## What to capture

For every experiment, capture:

```text
experiment id
parent experiment id
hypothesis
changed files
changed params
code/config diff
command run
stdout/stderr logs
metrics over time
final validation loss
runtime
throughput if available
failure reason if any
agent/human verdict
next decision/rationale
```

## Ideal replay story

A compelling replay is better than a perfectly optimized run.

Try to capture:

1. Baseline.
2. A scheduler or optimizer change that improves loss.
3. An aggressive change that fails or causes instability.
4. A learned constraint from the failure.
5. A branch that improves loss but hurts throughput.
6. A promoted branch that balances loss and runtime.
7. A forkable best node.

Example story:

```text
exp_000 baseline
exp_001 lower LR -> stable but slower
exp_002 cosine scheduler -> improves convergence
exp_003 high LR + scheduler -> NaN/instability
exp_004 agent learns LR upper bound
exp_005 optimizer tweak -> better val loss but lower throughput
exp_006 warmup adjustment -> best target-loss step
exp_007 fork from exp_006 with safer LR range
```

## Event conversion

If the run is not produced directly by Kun, convert it into Kun's event schema.

Minimum event sequence per experiment:

```text
experiment_proposed
file_diff_created
experiment_started
metric_logged*
experiment_finished or experiment_failed
evaluation_created
decision_created
```

Add `constraint_learned` events where useful.

## How honest should the replay be?

The tiny CNN path proves the live loop is real. The modded-nanogpt path should be based on real artifacts where possible.

Acceptable for hackathon demo:

- Real metrics with manually written hypotheses/rationales.
- Real diffs with manually summarized decisions.
- Partial real run expanded into a cleaner replay story, as long as you do not claim all branches were fully executed live during judging.

Avoid:

- Claiming leaderboard improvement if it did not happen.
- Pretending live modded-nanogpt execution is happening if it is replay/queued.
- Overpromising arbitrary repo support.

## Compute plan

### Plan A: DigitalOcean GPU

Use sponsor credits. Timebox setup.

Recommended timebox:

```text
60-90 minutes max to get GPU environment working.
```

If provisioning, quota, CUDA, or dependencies become slow, switch fallback.

### Plan B: Modal or Prime Intellect

Use if DigitalOcean setup is blocked.

Priority is reliability and fast setup, not cheapest possible GPU.

### Plan C: Partial/short run + replay shaping

If full serious run is hard:

- run fewer experiments
- use shorter mode
- capture real metrics from partial runs
- create a richer event replay around those artifacts

## modded-nanogpt adapter goals

### MVP

A converter/importer:

```text
logs/diffs/notes -> Kun events.jsonl
```

### Better

A semi-real adapter:

```text
mission spec -> run command -> parse metrics -> emit events
```

### Best

A first-class adapter:

```text
agent proposals -> code/config patch -> run experiment -> parse target-loss/throughput -> evaluate -> decide next branch
```

For hackathon, MVP or Better is enough if the tiny CNN live path works.

## Metrics to show

Useful metrics:

```text
validation loss
steps to target validation loss
wall-clock runtime
tokens/sec or throughput
NaN/instability detection
GPU utilization if easy
```

Do not overbuild. Validation loss + runtime/throughput is enough.

## Example event snippet

```json
{"event_id":"evt_001","timestamp":"2026-06-27T20:00:00Z","type":"experiment_proposed","mission_id":"modded_nanogpt_demo","experiment_id":"exp_006","branch_id":"branch_scheduler","parent_experiment_id":"exp_002","actor":{"type":"agent","name":"planner","model":"gpt-5.5"},"payload":{"hypothesis":"Longer warmup with cosine decay may preserve the convergence gains from exp_002 while reducing early instability.","changes":{"scheduler":"cosine","warmup_steps":300,"peak_lr":"lower_than_exp_003"},"expected_outcome":"Reach the target validation loss in fewer steps without NaNs.","risk":"A longer warmup may slow initial loss decrease.","rationale":"exp_002 improved convergence, while exp_003 showed instability with a more aggressive peak LR."}}
{"event_id":"evt_002","timestamp":"2026-06-27T20:00:05Z","type":"file_diff_created","mission_id":"modded_nanogpt_demo","experiment_id":"exp_006","branch_id":"branch_scheduler","payload":{"file_path":"train_gpt.py","diff":"--- train_gpt.py\n+++ train_gpt.py\n@@ ..."}}
{"event_id":"evt_003","timestamp":"2026-06-27T20:00:10Z","type":"experiment_started","mission_id":"modded_nanogpt_demo","experiment_id":"exp_006","branch_id":"branch_scheduler","payload":{"command":"torchrun ... train_gpt.py","workspace_path":"runs/modded_nanogpt/exp_006","timeout_sec":600}}
{"event_id":"evt_004","timestamp":"2026-06-27T20:01:10Z","type":"metric_logged","mission_id":"modded_nanogpt_demo","experiment_id":"exp_006","branch_id":"branch_scheduler","payload":{"name":"val_loss","value":3.41,"step":1000}}
{"event_id":"evt_005","timestamp":"2026-06-27T20:05:10Z","type":"experiment_finished","mission_id":"modded_nanogpt_demo","experiment_id":"exp_006","branch_id":"branch_scheduler","payload":{"status":"success","final_metrics":{"val_loss":3.25,"runtime_sec":294,"tokens_per_sec":123456}}}
{"event_id":"evt_006","timestamp":"2026-06-27T20:05:30Z","type":"evaluation_created","mission_id":"modded_nanogpt_demo","experiment_id":"exp_006","branch_id":"branch_scheduler","payload":{"verdict":"promote","summary":"This run reached the target loss earlier than the parent while staying stable.","evidence":["Target validation loss crossed earlier than exp_002","No NaNs observed","Throughput regression was within acceptable range"],"concerns":["Needs repeat with another seed"]}}
```

## Final checklist for the replay

Before demo, confirm:

- [ ] replay loads without errors
- [ ] graph is visually rich
- [ ] at least one node has a good diff
- [ ] at least one node has a clear failure
- [ ] at least one learned constraint is visible
- [ ] best node is obvious
- [ ] fork from node works visually
- [ ] no unsupported claims in narration
