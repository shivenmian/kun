# agent_edit_real.events.jsonl — honesty guard

**This replay is REAL.** Kun's merged agent-edit patcher
(`backend/app/loop/patcher.py` — the Claude Code CLI run headless as a coding-agent
subprocess, editor model **haiku**) edited the **real source code** of
[`agent_edit_target/target.py`](agent_edit_target/target.py) across 3 experiments.
**The diffs and the metrics are REAL** — every `file_diff_created` carries the actual
`git diff` the coding agent produced, and every accuracy was captured by **actually
executing the edited code on CPU** (`python target.py`, numpy only — **no GPU, no
torch, no network**). Nothing here is hand-authored or synthesized.

**It is a small stand-in target, not nanogpt.** The target is a tiny 1-hidden-layer
numpy MLP on a deterministic concentric-circles dataset, chosen so a full
agent-edit → run → evaluate cycle takes well under a second on a laptop. It
demonstrates the *genuine* agent-edit loop end-to-end; it is not a large model and
not a GPU run. (The heavy modded-nanogpt trajectory is the separate, clearly-labelled
synthesized stand-in: `nanogpt.events.jsonl` / `nanogpt.README.md`.)

No experiment fell back or flaked: all 3 agent edits applied cleanly (the patcher
returned `ok=True` with a non-empty diff each time) and all 3 edited programs ran to
completion. Total editor cost for the recorded run: **~$0.04 USD** (haiku, 3 edits).

## How it was produced

```
KUN_EDITOR_MODEL=haiku python scripts/record_agent_edit_run.py
```

The recorder ([`scripts/record_agent_edit_run.py`](../../scripts/record_agent_edit_run.py)):

1. Runs the **unedited** `target.py` as the baseline (`exp_000`).
2. For each of `exp_001..003`, builds a concrete single-change proposal
   (`types.SimpleNamespace`) and calls
   `agent_edit.apply(workspace=..., proposal=..., constraints=[],
   editable_files=["target.py"], model="haiku", source_dir=<prev edited copy>)` —
   the **real** merged patcher. Edits **accumulate**: each experiment's `source_dir`
   is the previous experiment's edited sandbox, so each captured diff is a single,
   clean, code-level change.
3. Copies the edited `target.py` out of the sandbox and **executes it**
   (`subprocess`, timeout) to parse the real `METRIC accuracy=...` from stdout.
4. Emits genuine Kun events via `kun_log` (no new event types; envelope/order match
   `sample.events.jsonl`). `file_diff_created` also carries the real `commit_sha`,
   `session_id`, and `cost_usd` from the patcher.

Re-running re-drives the live editor, so the exact diffs/costs (and conceivably a
metric) can vary slightly between captures — the numbers committed here are from one
real recorded run. If a future edit ever regresses or flakes, the recorder logs it
**as-is** (`experiment_failed` / `reject`); it never fakes a number.

## The real-code knob

`target.py`'s behavior is controlled entirely by **code-level** knobs (no config file):

- `def activation(x)` — the hidden-layer nonlinearity. Default is the **identity**
  (linear) map, so the network collapses to a linear classifier and is stuck near
  chance on the not-linearly-separable concentric circles. Its gradient is computed
  numerically (central difference) so changing **only** this function body is a
  complete, self-consistent edit.
- `HIDDEN_SIZE`, `LEARNING_RATE`, `EPOCHS` — numeric source constants (capacity / SGD).

## Trajectory arc (REAL captured numbers)

Objective: **maximize** test `accuracy`, target 0.95.

| exp | operator | real agent edit | accuracy | outcome |
|---|---|---|---|---|
| exp_000 | draft | baseline (identity activation, `HIDDEN_SIZE=3`) — run as-is | 0.4333 | valid (near chance, as expected) |
| exp_001 | improve | `activation`: `return x` → `return np.tanh(x)` | 0.8444 | valid (**+0.41 improvement**) |
| exp_002 | improve | `HIDDEN_SIZE`: 3 → 8 | 0.9333 | valid (+0.089 improvement) |
| exp_003 | improve | `HIDDEN_SIZE`: 8 → 16 | 0.9667 | valid (**overall best node**) |

- **Improvements:** exp_001 (nonlinearity is the dominant lever), exp_002, exp_003.
- **Best node:** exp_003 (accuracy 0.9667), forkable.
- A linear model fundamentally cannot separate an inner disk from a surrounding ring,
  which is why introducing `np.tanh` is the single most impactful edit (0.43 → 0.84).

The one real captured diff for `exp_001` (verbatim from the patcher's `git diff`):

```diff
diff --git a/target.py b/target.py
--- a/target.py
+++ b/target.py
@@ -34,7 +34,7 @@ def activation(x):
     concentric-circles dataset. Swapping this for a real nonlinearity (e.g.
     ``np.tanh(x)``) is the single most impactful edit.
     """
-    return x
+    return np.tanh(x)
```
