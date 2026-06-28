# Kun — Operator Checklist (what's left outside the implementation)

The app build is handled by the implementation agent(s) (see the handover prompt + docs 00 and 06).
These are the **human/ops tasks a coding agent can't do** — run them around/alongside the build.

## Already done (don't redo)
- **Asset A** — rich sample trajectory: `examples/replays/sample.events.jsonl` (committed; regenerate via `scripts/gen_sample_events.py`).
- **Asset C** — independent producer (the wedge proof): `examples/external_loop_demo.py`.
- The open-contract helper: `kun/log.py`. The Asset B converter scaffold: `scripts/convert_nanogpt.py`.

## You own these

### 1. Provider API keys (needed for P0 + P2)
- Put `ANTHROPIC_API_KEY` (and any other provider keys LiteLLM routes to) in the backend env / `.env`.
- The LLM-driven loop (P0) and benchmarking (P2) need this. No key → the loop falls back to the heuristic baseline (it still runs, but it's not the real story).

### 2. GPU for the serious run (Asset B)
- Plan A: **DigitalOcean** GPU, **60–90 min setup timebox** → fall back to Modal / Prime Intellect → partial-run + replay-shaping. Full runbook + compute plan: **doc 07**. (Confirmed: DigitalOcean, not local CUDA.)

### 3. Asset B — the serious nanogpt run (real compute; the one asset that isn't fully scripted)
Two paths (docs 07 / 08):
- **Preferred — Kun-driven (Mode A + `agent-edit`):** needs P1 built; Kun edits nanogpt's real code overnight and emits events directly (no converter).
- **Fallback — external session (can run NOW, in parallel with the build):** run a Claude Code / Codex session on nanogpt on the GPU box, capture artifacts (git diffs, training logs, the markdown harness), then convert with `scripts/convert_nanogpt.py` (fill `ATTEMPTS` from the real numbers, or wire `parse_run_dir()`).
- **Recommendation:** kick off the external run **in parallel, early** — it's a hedge that doesn't depend on the build finishing, and it's recorded (not live), so timing is flexible.
- **Honesty guard:** narrate exactly what produced it (Kun-driven vs ingested); never imply live execution or a leaderboard win that didn't happen. Aim for a **rich** trajectory (≥1 improvement, ≥1 failure/NaN, a clear best/forkable node) — a compelling trajectory beats a good score.

### 4. The `agent-edit` spike (pre-P1, ~30 min)
- Before building P1, run the spike in **doc 08 §9** to confirm the Claude Code headless flags against your installed CLI. (Can be the implementation agent's first P1 task, or you.)

### 5. Demo prep (end; Workstream F)
- Rehearse the **5 beats** (spec §8); pin the demo machine + seeds; capture **backup recordings/screenshots** (live training can flake on stage).

## Decisions you own (not blockers)
- `$KUN_EDITOR_MODEL` for `agent-edit` (may differ from the planner model).
- Which model(s) to benchmark (P2).
- Worktrees-per-parallel-agent vs single-stream (doc 06 recommends worktrees for parallel build agents; your manual commits go to `main`).
