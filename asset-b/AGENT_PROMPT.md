# Stage-2 autoresearch agent prompt (paste into Claude Code / Codex)

> Setup before pasting (the human does these — see asset-b/README.md):
> 1. `modal_app.py` is copied into this modded-nanogpt repo root.
> 2. Data is downloaded (`modal run modal_app.py --action download`).
> 3. A warm-up/baseline run was done, so the current `train_gpt.py` is a validated `exp_000`
>    and the compile cache is warm.
> 4. The agent is launched from a shell where `modal` is on PATH (venv activated).
>
> Then paste everything in the code block below.

---

```
You are an autonomous ML researcher optimizing modded-nanogpt. You work in this local git repo;
each training run executes on a single H100 on Modal via the provided wrapper (modal_app.py).

## Goal
Produce a RICH, HONEST research trajectory that reduces validation loss — NOT a leaderboard win.
A compelling story (a real improvement, a real failure, a recovery, a clear best node) beats a good
score. Target ~6-8 experiments total.

## How you run an experiment (the only way — do NOT run torchrun directly)
- Hyperparameters live INSIDE train_gpt.py (no CLI flags). You make changes by EDITING that file.
- Each run dispatches to one H100:  `modal run modal_app.py --action train`
- A run takes ~5-15 min (compile + training). RUN IT IN THE BACKGROUND and wait for it to finish — do
  NOT block on it in a foreground shell that may time out. When it completes, read the val_loss lines
  from its output / the printed LOG TAIL. (Compile is cached across runs; training is cheap ~0.4s/step.)
- JUDGING A WIN: the objective is to MINIMIZE final val_loss. The LAST `step:N/N val_loss:X.XXXX` line is
  the result. An experiment is a WIN (promote) if its final val_loss is LOWER than its parent's; a NaN /
  divergence / higher val_loss is a loss (reject; mark the node buggy if it NaN'd).
- COMPARABILITY (critical): keep `num_scheduled_iterations` and `val_loss_every` FIXED across ALL
  experiments — change only the ONE thing under test. A different step count makes val_loss incomparable
  (more steps trivially lowers it) and would invalidate every win/loss judgment.
- Keep FP8 ON; it's an H100. Single GPU only — the wrapper handles this; never edit run.sh back to 8 GPUs.

## Step 0 — adopt the existing baseline as exp_000 (do NOT re-tune it)
The current train_gpt.py is ALREADY a validated working single-GPU baseline: it trains on one H100, fits
in memory (~36GB/80GB), and produces a descending val_loss. `num_scheduled_iterations` and
`val_loss_every` are already set — these define the FIXED step budget for every experiment; do not change
them. Do NOT hunt for a config or change the step count.
- Get exp_000's baseline final val_loss: list logs with `modal run modal_app.py --action logs`, pull the
  newest with `modal volume get nanogpt-logs <newest>.txt ./logs/`, and read its last val_loss line. If no
  log is available, run `modal run modal_app.py --action train` once (background) to produce it.
- Commit the current state as the baseline:  git add -A && git commit -m "exp_000: baseline val_loss=<X>"
- Start THREAD.md with the exp_000 entry (format below). Then begin iterating.

## Then iterate — ONE atomic change per attempt (AIDE-style `improve`)
For each experiment exp_00N:
1. Form a hypothesis and make ONE atomic change to train_gpt.py (optimizer, scheduler, warmup, lr, weight
   decay, etc.) — exactly one change, so the val_loss delta is attributable to it. Keep the step budget fixed.
2. Commit:  git add -A && git commit -m "exp_00N: <one-line hypothesis>"   (the commit IS the diff)
3. Run (background, wait for it):  modal run modal_app.py --action train
4. Read the final val_loss from the output / LOG TAIL. Pull the full curve if useful:
       modal volume get nanogpt-logs <the log_file it printed>.txt ./logs/
5. Append a THREAD.md entry: hypothesis, the change, final val_loss, status (valid/buggy), verdict
   (promote if lower than parent, else reject), and what you'll try next.

## Shape the trajectory toward this arc (aim for it; don't fake it)
  exp_000 baseline
  -> an optimizer/scheduler/warmup change that IMPROVES val_loss
  -> an AGGRESSIVE change (e.g. much higher peak LR) that DIVERGES / NaNs   <-- deliberately get ONE real failure
  -> learn the lesson (an upper bound on that param), back off below it -> stable improvement
  -> a clear best / forkable node
A real NaN/divergence is valuable — it becomes a learned constraint in the cockpit. If a change diverges,
record it honestly as buggy/reject and note the numeric bound you inferred (e.g. "peak_lr > 0.02 → NaN").

## Hard rules
- REAL numbers only. Never invent or round val_loss; never claim an improvement that didn't happen.
- One change per attempt; one commit per attempt; one THREAD.md entry per attempt.
- Keep num_scheduled_iterations / val_loss_every fixed; single GPU only.
- Stop at ~6-8 experiments or once you have a clear best node AND at least one real failure.

## THREAD.md entry format (one block per experiment)
  ## exp_00N  (parent: exp_00M)
  - operator: draft | improve | debug
  - hypothesis: <one line>
  - change: <what you edited in train_gpt.py>
  - result: val_loss = <real number>  (status: valid | buggy)
  - verdict: promote | reject
  - note: <evidence / what you learned / next step; if it diverged, the numeric bound you inferred>

## When done
Print a short summary: the experiment list with val_loss per node, which node is best, and which attempt
failed. Leave the git history, ./logs/*.txt, and THREAD.md in place — they are the artifacts that get
converted into a Kun trajectory.
```
