# modded-nanogpt Runbook for Kun

> **Reconciled with [`00-spec.md`](00-spec.md) (canonical; wins on conflict).** v4 deltas: nanogpt can now be **DRIVEN by Kun** — the **preferred Beat 1 is a recorded Kun-driven (Mode A + `agent-edit`) run** ("Kun drove this itself"), where Kun orchestrates Claude Code/Codex to edit nanogpt's real training code (planner → patcher → runner → parser → evaluator → decider). External-session → convert (Mode B ingest) is the **FALLBACK**. The former "Better/Best" Kun-driven adapters are no longer post-MVP — they are the v4 Mode-A path that `agent-edit` (P1) enables. Both paths produce conformant events via Kun's **open logging contract** (doc 03) incl. `operator` (draft/debug/improve) + `schema_version`. This run is **Demo Beat 1 (serious run on real code, the credibility beat)** — the dedicated wedge beat (Beat 2) is a separate ~15-line independent script. Honesty guard: narrate exactly what happened (Kun-driven vs ingested); never imply live execution that didn't occur. Because the real-code cycle is minutes & nondeterministic, it is shown as a **recorded** run, not live on stage. Compute: DigitalOcean Plan A (**confirmed** — not local CUDA; 60–90 min timebox) → Modal/Prime Intellect → partial+replay-shaping (spec §11).

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

Do not depend on *live* modded-nanogpt execution during judging — the Kun-driven (`agent-edit`) cycle on real code is minutes & nondeterministic, so show it as a **recorded** Mode-A run, not live on stage (spec §4 risk, §11).

**This run is the demo's serious "real code" credibility beat (Beat 1).** Preferred framing (Mode A): "Kun drove this autoresearch session itself — it used `agent-edit` to edit nanogpt's real training code." Fallback framing (Mode B): "this was a Claude-Code-driven run; ~5 lines pipe it into Kun." Either way the events MUST conform to Kun's open logging contract / event schema (doc 03) so the session loads exactly like any other trajectory. (The dedicated wedge beat — Beat 2 — is a separate, trivial ~15-line independent script, decoupled from this GPU run; see spec §8.)

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
operator (draft/debug/improve)
schema_version (envelope, =1)
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

If the run was *not* produced directly by Kun's own loop (i.e., the Mode-B fallback), convert it into Kun's event schema. (The preferred Mode-A path emits these events directly via `kun_log`.)

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

When converting, every event envelope must include `schema_version` (=1), and each `experiment_proposed` must carry an `operator` (`draft`/`debug`/`improve`). Outcomes map to the cockpit's node-lifecycle vocabulary: `experiment_finished`(success) → `valid`, `experiment_failed` → `buggy` (the `debug` operator targets buggy nodes). Emit `constraint_learned` so failures feed the research-memory panel.

## How honest should the replay be?

The tiny CNN path proves the live loop is real. The modded-nanogpt path should be based on real artifacts where possible.

Acceptable for hackathon demo:

- Real metrics with manually written hypotheses/rationales.
- Real diffs with manually summarized decisions.
- Partial real run expanded into a cleaner replay story, as long as you do not claim all branches were fully executed live during judging.

Avoid:

- Claiming leaderboard improvement if it did not happen.
- Pretending live modded-nanogpt execution is happening if it is replay/queued.
- Mislabeling which path produced the run, or implying *live* execution that didn't occur. Narrate exactly what happened: a recorded **Kun-driven (Mode-A `agent-edit`)** run if Kun drove it, or a recorded **external run ingested via the open contract** (Mode B) if an external agent produced it. Both are honest; the only sin is claiming live execution, or a leaderboard improvement, that didn't happen.
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

**v4:** the **preferred** path is **Kun-driven (Mode A + `agent-edit`, P1)** — Kun edits nanogpt's real training code (the "semi-real"/"first-class" adapters below; recorded overnight, not live). The **converter/importer is the Mode-B fallback** (when Kun didn't drive the run). The reliable *live* loop is shown on tiny CNN with `config-patch` (Beat 3).

### Mode-B fallback — converter/importer (when Kun didn't drive the run)

A converter/importer:

```text
logs/diffs/notes -> Kun events.jsonl
```

### Mode-A (preferred, P1) — semi-real Kun-driven adapter

Kun's own loop drives nanogpt (recorded overnight, not live):

```text
mission spec -> run command -> parse metrics -> emit events
```

### Mode-A (preferred, P1) — full first-class Kun-driven adapter

The complete Kun-driven loop (via `agent-edit`):

```text
agent proposals -> code/config patch -> run experiment -> parse target-loss/throughput -> evaluate -> decide next branch
```

For the hackathon, the **recorded Kun-driven (`agent-edit`) run is the preferred target for nanogpt** (Beat 1); the converter is the Mode-B fallback. The reliable *live* loop is demonstrated on the tiny CNN with `config-patch` (Beat 3).

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

> Every envelope below also needs `"schema_version":1` (kept off some lines here only for brevity). Each `experiment_proposed` carries an `operator`.

```json
{"event_id":"evt_001","timestamp":"2026-06-27T20:00:00Z","type":"experiment_proposed","mission_id":"modded_nanogpt_demo","experiment_id":"exp_006","branch_id":"branch_scheduler","parent_experiment_id":"exp_002","actor":{"type":"agent","name":"planner","model":"gpt-5.5"},"payload":{"operator":"improve","hypothesis":"Longer warmup with cosine decay may preserve the convergence gains from exp_002 while reducing early instability.","changes":{"scheduler":"cosine","warmup_steps":300,"peak_lr":"lower_than_exp_003"},"expected_outcome":"Reach the target validation loss in fewer steps without NaNs.","risk":"A longer warmup may slow initial loss decrease.","rationale":"exp_002 improved convergence, while exp_003 showed instability with a more aggressive peak LR."}}
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
