# Asset B — the serious nanogpt run (Mode-B fallback, recorded)

The credibility demo beat (Beat 1): a *real* autoresearch session on modded-nanogpt, edited
on real training code, captured as artifacts, then converted into a Kun trajectory. This is
the **external / Mode-B** path (an external agent drives nanogpt; we ingest via the open
contract) — the preferred Mode-A path needs P1, which doesn't exist yet.

**Brain/muscle split:** the agent + repo live on your **laptop** (free); each experiment runs
on **one H100 on Modal** (billed per-second, no idle charge). You only pay during training.

Files here:
- `modal_app.py` — the Modal wrapper (copy into your modded-nanogpt clone root).
- `AGENT_PROMPT.md` — paste into the Stage-2 autoresearch agent (Claude Code / Codex).

---

## One-time setup (~laptop)

```bash
# 1. Clone modded-nanogpt somewhere on your laptop (NOT inside the kun repo)
git clone https://github.com/KellerJordan/modded-nanogpt.git
cd modded-nanogpt

# 2. Drop the wrapper in the repo root
cp /Users/shivenmian/kun/asset-b/modal_app.py .

# 3. Modal client (your account + $250 credits are already set up)
pip install modal
modal token new            # if not already authenticated

# 4. Download a few FineWeb chunks to a persistent Modal Volume (once; ~minutes)
modal run modal_app.py --action download --num-chunks 8
```

## The loop (per experiment) — the agent does this, not you

```bash
# edit train_gpt.py locally (hypothesis -> one change), then:
git add -A && git commit -m "exp_00N: <hypothesis>"     # one commit per attempt = the diff
modal run modal_app.py --action train                   # trains current train_gpt.py on 1x H100
# read val_loss from the printed LOG TAIL; record the result in THREAD.md; decide next change
```

Pull a full run log back for the converter when you want the whole curve (use the exact
`log_file` name that the `train` command prints):
```bash
modal volume get nanogpt-logs <log_file>.txt ./logs/
```

## Key facts baked into the wrapper (verified against the current repo)
- `run.sh` is 8-GPU; the wrapper forces `--nproc_per_node=1`. `grad_accum_steps = 8 // world_size`,
  so **1 GPU keeps the same effective batch** (memory is fine; it's just ~8× slower wall-clock).
- **Hyperparameters live inside `train_gpt.py`** (no CLI flags) — the agent edits the file directly,
  and the script self-logs its own source into `logs/<run_id>.txt`. Ideal for agent-edit.
- **Set `num_scheduled_iterations` high enough to LEARN.** val_loss starts ~10.83 (random init); ~50
  steps stay flat. Training is cheap (~0.4s/step) and the compile cache is persisted, so use ~600-1380
  steps for a real descending curve. (50 iters / `val_loss_every=25` is fine only as a pipeline smoke test.)
- **Compile dominates, but is cached + streamed.** The FIRST train run compiles ~20 min on one GPU; later
  runs are much faster because `TORCHINDUCTOR_CACHE_DIR` / `TRITON_CACHE_DIR` live on a persistent Volume
  (`nanogpt-compile-cache`). Run output now STREAMS live to the terminal instead of buffering.
- The **first `modal run` builds the image** (CUDA 12.8 + torch nightly cu128) once — several minutes,
  one-time, not GPU-billed. Subsequent runs reuse it; only your edited `train_gpt.py` re-uploads.
- **Memory fits comfortably**: a single-GPU run peaks ~36 GB of 80 GB. (If a much larger config ever
  OOMs, the repo's remedy is to reduce the FlexAttention sequence length / `val_batch_size`.)
- Keep **FP8 ON** (H100 is Hopper). `--disable-fp8` exists only for non-Hopper cards.
- Cost: H100 ≈ $3.95/hr. First run ~20 min compile; cached runs ~10 min. ~8 attempts ≈ **~$6-10** of
  your $250. The `train` function has a **45-min timeout** as a runaway-cost guard (~$3 max/run).
- **No idle charges, but**: don't leave a `modal shell --gpu` open — use the function dispatch above.

## When the run is done → convert to a Kun trajectory
You'll have, on your laptop: git history (one commit per attempt), `logs/*.txt` (real val_loss
curves), and `THREAD.md` (hypotheses/verdicts). Feed them to the converter in the kun repo:

```bash
cd /Users/shivenmian/kun
# Recommended: hand-fill the ATTEMPTS list in scripts/convert_nanogpt.py with the real numbers
#   (git show <sha> for each diff; val_loss from logs/*.txt), then:
python scripts/convert_nanogpt.py -o examples/replays/nanogpt.events.jsonl
# (or wire parse_run_dir() to auto-parse ./logs + git history)
```

The output drops into `examples/replays/` and loads in the cockpit like any other replay.
**Honesty guard:** narrate it as an external run ingested via the open contract — not Kun-driven, not live.
