# nanogpt.events.jsonl — honesty guard

**This replay (`nanogpt.events.jsonl`) is a SYNTHESIZED, hand-authored trajectory — NOT a
captured GPU run.** It is a realistic, internally-consistent stand-in for the overnight
modded-nanogpt Mode-A + agent-edit run, produced so the demo (Beat 1) is never blocked on an
external/ops GPU dependency. No training was executed to create it; the diffs, val-loss curves,
throughput, and runtimes are plausible stand-ins authored from realistic modded-nanogpt numbers
(GPT-2 124M on FineWeb, ~120k tokens/sec on 8×H100, ~10 min/run, target val_loss 3.28). **Do not
present these numbers as a real, captured run.**

It is a **drop-in placeholder**: the same converter (`scripts/convert_nanogpt.py`) will ingest the
REAL run's artifacts (`--run-dir`, via `parse_run_dir()`) and regenerate this exact file with real
numbers the moment that run is recorded. Nothing downstream changes — only the data.

## How it was produced

```
python scripts/convert_nanogpt.py -o examples/replays/nanogpt.events.jsonl
```

The converter emits the hand-authored `ATTEMPTS` / `FORKS` lists in `scripts/convert_nanogpt.py`
through the same envelope/`event_id`/`timestamp` conventions as
`examples/replays/sample.events.jsonl`. Every event type is from `docs/03-event-schema.md` (no new
types). It prints a loud notice that the output is synthesized.

## Trajectory arc

Objective: minimize `val_loss`, target **3.28**. Each experiment = one attempted change.

| exp | branch | operator | change | val_loss | outcome |
|---|---|---|---|---|---|
| exp_000 | main | draft | AdamW baseline | 3.40 | valid |
| exp_001 | main | improve | **Muon optimizer** on 2D hidden matrices | 3.30 | valid (improvement) |
| exp_002 | main | improve | Muon LR → 0.05 (too aggressive) | NaN | **failed / NaN** → learned `muon_lr > 0.025` bound |
| exp_003 | main | improve | back off Muon LR to 0.024 + 256-step warmup | 3.27 | valid (crosses target) |
| exp_004 | main | improve | **QK-norm** in attention | 3.245 | valid (best on main) → **forked from here** |
| exp_005 | main | improve | learned absolute pos-emb (drop RoPE) | 3.29 | rejected (regression) |
| exp_006 | human fork | improve | logit soft-cap (cap 15) | **3.238** | valid (**overall best node**) |

- **Improvements:** exp_001 (Muon), exp_003 (warmup/backoff), exp_004 (QK-norm), exp_006 (soft-cap).
- **Failure/NaN:** exp_002 — emits `experiment_failed{nan_detected}` + a deterministic
  `constraint_learned` (`muon_lr > 0.025`, the CONTRACT §3 NaN→x·0.5 rule).
- **Best / forkable node:** exp_006 is the overall best (val_loss 3.238); exp_004 is the explicit
  human **fork point** (`fork_created` + `branch_created` + human `constraint_added`).

## When the real run lands

Wire `parse_run_dir()` in `scripts/convert_nanogpt.py` to the captured artifacts (one `Attempt`
per commit, `diff = git show <sha> -- train_gpt.py`, metrics parsed from the training logs) and
re-run with `--run-dir`. This file is then regenerated from real data and this README updated to
say so.
