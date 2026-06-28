# live_steering_dod5.events.jsonl — REAL live Mode-A capture (DoD #5)

**This replay is REAL.** It is the verbatim `runs/<id>/events.jsonl` of an actual live Mode-A
mission captured on 2026-06-28 — real tiny-CNN training (Fashion-MNIST, CPU, ~5s/run), real
NaN, real underfitting, real deterministically-learned constraints. Nothing is hand-authored.

## What it demonstrates (the closed constraint loop, steered live)

A human steered the live mission through the **approval gate** to elicit failures, then let the
planner propose on its own:

| exp | action | real outcome |
|---|---|---|
| `exp_000` | approved (baseline) | val_accuracy 0.799 — the parent |
| `exp_001` | human reject → replacement `learning_rate: 0.05` | **NaN** → `learned_001`: ban `learning_rate > 0.025` (confidence high) |
| `exp_002` | human reject → replacement `dropout: 0.9` | **underfit** (train 0.40 / val 0.644 both dropped) → `learned_002`: ban `dropout > 0.72` (confidence **medium**) — a NON-NaN learned constraint |
| `exp_003` | human reject → replacement `dropout: 0.85` | underfit again → **merged** into `learned_002` → ban `dropout > 0.68`, confidence **medium → high** (memory sharpened) |
| `exp_004`, `exp_005` | **approved as-is (planner-authored)** | proposals respect BOTH learned bounds (dropout 0.15/0.1, lr 0.002) — the loop was reshaped |

Also emitted live: two SOFT positive lessons (`learned_003/004`, e.g. "+0.022 val_accuracy")
from promotions — the two-tier research memory (hard bounds + bias-only lessons) working end to end.

## Honesty notes

- The high-LR and high-dropout experiments were **human-forced** via the approval gate's
  reject-with-replacement (visible as `experiment_rejected` with a human actor) — this is the
  intended steering surface, used to drive the model into the failure regimes quickly.
- The **reshape evidence** is `exp_004`/`exp_005`: those are the *planner's own* proposals
  (approved unchanged) and they respect the learned bounds — i.e. the constraints, not the human,
  shaped them.
- Every metric, NaN, and constraint here was produced by the real loop; the deterministic
  generators/hard-reject are additionally covered by unit tests (`backend/app/loop/test_*.py`).

Load it like any replay (`?replay`) or via the state builder.
