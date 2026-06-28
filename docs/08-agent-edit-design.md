# Kun `agent-edit` Patcher — Design Note

> The one component that needs design-before-code. Read before starting P1.
> Canonical context: [`00-spec.md`](00-spec.md) §4 (the patcher), §11 (risk). This note details the *how*.
>
> **Invocation flags verified** against the Claude Code docs (current as of June 2026). A couple of items remain version-sensitive — still run the 30-min spike (§9) to confirm against the installed CLI before P1.

## 1. What it is and where it fits

The **patcher** is one interface with two implementations (spec §4):

- **`config-patch` (P0)** — writes changed keys into a config file. Reliable, seconds/cycle. The always-available fallback.
- **`agent-edit` (P1)** — hands the LLM planner's proposed change to a **coding agent (Claude Code / Codex) run as a subprocess** to edit *real model code*, then returns the diff. This is what lets Kun autoresearch any model (e.g. nanogpt: new optimizers, attention tweaks), not just config knobs.

It sits inside Kun's **Mode A** loop: `planner → patcher(agent-edit) → runner → parser → evaluator → decider`. The planner decides *what* to try (hypothesis + change description); `agent-edit` is the *hands* that turn that into a concrete code edit.

**Division of labor (important):** the planner is the researcher; the coding agent is a *mechanical editor*. Do **not** ask the coding agent to invent the research direction — pass it a specific, bounded change to implement. This keeps the trajectory attributable (one node = one intended change) and keeps the coding agent's nondeterminism contained.

## 2. Interface

Maps onto `ProjectAdapter.apply_changes` (doc 02). Suggested shape:

```python
@dataclass
class PatchResult:
    ok: bool                 # did the agent produce a valid, applied edit?
    diff: str                # unified diff of the workspace (git diff)
    files_changed: list[str]
    commit_sha: str | None   # if commit-per-node is on
    error: str | None        # populated when ok is False (→ buggy node)

class Patcher(Protocol):
    def apply(self, workspace: Path, proposal: Proposal, constraints: list[Constraint]) -> PatchResult: ...
```

`agent-edit.apply()`:
1. Build the editing prompt from `proposal` (§3).
2. Invoke the coding agent as a subprocess in `workspace` (§4).
3. Capture `git diff`; validate (§5); optionally commit (§6).
4. Return `PatchResult` → the loop emits `file_diff_created` (the real diff) and proceeds to the runner. On `ok=False`, the node becomes `buggy` and the `debug` operator targets it next.

## 3. The editing prompt (what Kun hands the coding agent)

Keep it tight and bounded. Include:

- **The change to implement** — `proposal.hypothesis` + `proposal.changes` (the concrete edit, e.g. "replace the AdamW optimizer with a Muon optimizer in the training loop").
- **Operator discipline** — for `improve`: *"Make exactly ONE atomic change so its effect is measurable. Do not refactor or change anything else."* For `debug`: *"The previous run failed with: `<error/trace>`. Fix it while preserving the approach."* For `draft`: the new approach to scaffold.
- **Editable surface** — `mission.editable_files` (which files it may touch). *"Edit only these files."*
- **Active constraints** — the structured `bound`s and constraint text, e.g. *"Do NOT set learning_rate > 0.003."* (This is belt-and-suspenders; the planner already hard-rejects bound violations, but telling the editor keeps it from fighting you.)
- **Do-not** — *"Do not run training. Do not commit. Do not touch files outside the editable set. Make the change and stop."*

Kun runs the train/eval itself (the runner) — the coding agent only edits.

## 4. Invocation (subprocess)

Run the agent **non-interactively, in the per-experiment workspace dir, with a turn cap and a wall-clock timeout.** Recommended: **Claude Code headless ("print") mode** (the environment is Claude Code).

### Option A — Claude Code CLI (recommended)

```bash
claude -p "<editing prompt>" \
  --bare \                              # skip hooks/skills/plugins/MCP/memory/CLAUDE.md -> reproducible, fast
  --permission-mode acceptEdits \       # auto-approve file edits, no interactive prompts
  --allowedTools "Read,Edit,Write" \    # comma-separated; NO Bash -> the agent edits but can't run/commit
  --max-turns 12 \                      # bound the agentic loop
  --output-format json \                # structured result: .result, .total_cost_usd, .usage, .session_id
  --max-budget-usd 1.00 \               # optional hard cost cap per edit
  --model "$KUN_EDITOR_MODEL"           # alias (opus/sonnet/haiku/fable) or full id; may differ from planner
# launch the subprocess with cwd = the experiment workspace; wrap in a wall-clock timeout
```

- **No `--cwd` flag** — Claude operates in the process's working directory, so launch the subprocess with `cwd=workspace` (or `cd workspace && claude ...`). All edits land in the sandbox.
- **`--allowedTools` overrides the permission mode**, so list exactly what the editor may use. `Read,Edit,Write` lets it edit code; **withholding `Bash`** means it cannot run training or commit — Kun owns both. (If an edit genuinely needs a shell, allow a narrow `Bash(<pattern>)`, never blanket `Bash`.)
- `--bare` is recommended for scripted runs (skips context auto-discovery → reproducible).
- `--output-format json` → log `total_cost_usd` / `usage` / `session_id` onto the node.

### Option B — Claude Agent SDK (Python)

```python
# pip install claude-agent-sdk     (Python 3.10+; async)
from claude_agent_sdk import query, ClaudeAgentOptions

options = ClaudeAgentOptions(
    cwd=str(workspace),                   # absolute path to the per-experiment workspace
    permission_mode="acceptEdits",
    allowed_tools=["Read", "Edit", "Write"],
    max_turns=12,
    max_budget_usd=1.00,
    model=os.environ["KUN_EDITOR_MODEL"],
    system_prompt="You are a mechanical code editor. Make exactly the requested change; do not run anything.",
)
async for message in query(prompt=editing_prompt, options=options):
    ...  # iterate to completion; the SDK applies edits in cwd. Read ResultMessage for usage/cost.
```

Prefer the SDK if Kun's backend is already async Python and you want structured streaming; prefer the CLI for simplicity and isolation.

### Option C — Codex CLI (fallback editor)

```bash
codex exec "<editing prompt>" --sandbox workspace-write --ask-for-approval never   # non-interactive, auto-approve in-workspace edits
```

Keep the editor pluggable behind `agent-edit` so the choice of Claude Code vs Codex is config, not code.

## 5. Sandboxing, capture & validation

- **Workspace = an isolated copy per experiment.** Use a `git worktree` (or a copied dir that is its own git repo) rooted at the mission's base commit. The agent edits only here; nothing touches the user's main tree.
- **Capture the diff** after the subprocess returns: `git -C <workspace> diff` (vs the experiment's base commit). That string → `file_diff_created.payload.diff`.
- **Validate `ok`:**
  - **No diff** → `ok=False, error="agent made no change"` → `buggy`.
  - **Edited a file outside `editable_files`** → reject/revert those paths (or fail) — enforce the editable surface.
  - **Syntactically broken** (optional cheap check: `python -m py_compile` on changed `.py`) → can mark buggy early without spending a training run.
  - Otherwise `ok=True`; the runner decides true success/failure from the actual train/eval (NaN/crash → `experiment_failed` → `buggy`).
- **Timeout/kill:** wrap the subprocess in a hard wall-clock timeout (`timeout_sec` from the mission/budget). On timeout, kill the process group, `ok=False, error="editor timed out"` → `buggy`.

## 6. commit-per-node (P1) interaction

If commit-per-node is on: after a valid edit, `git -C <workspace> add -A && git commit` on the experiment's branch; store the `commit_sha` on the node. This makes "fork" literally `git branch` from that sha and gives real diffs for free. `agent-edit` + commit-per-node + git-worktree workspaces compose cleanly — the trajectory becomes a real git DAG.

## 7. Failure modes & fallbacks (designed in, not hoped for)

| Failure | Detection | Response |
|---|---|---|
| Agent makes no change | empty `git diff` | `buggy` node; planner may `debug` or move on |
| Agent edits out-of-scope files | path check vs `editable_files` | revert those paths or fail → `buggy` |
| Agent breaks the code | `py_compile` and/or the train run crashes | `buggy`; `debug` operator gets the trace |
| Editor times out / hangs | wall-clock timeout | kill process group → `buggy` |
| Editor unavailable / no key | subprocess error | **fall back to `config-patch`** for that mission; loop keeps running |
| Nondeterministic / slow cycle | inherent | demo-time: use **recorded** runs for heavy targets; live only on fast targets |

The loop never hard-fails: a bad `agent-edit` produces a `buggy` node (which is *part of the trajectory story*), and `config-patch` is always available as the reliable path.

## 8. Demo & timeboxing (from spec §11)

- An `agent-edit` → train → eval cycle on **real code is minutes-long and nondeterministic.** So:
  - **Live on stage:** `agent-edit` only on a **fast/small target** (or `config-patch` on tiny CNN). One cycle should be seconds, not minutes.
  - **The heavy real-code run (nanogpt) is RECORDED** (Asset B, overnight) — "Kun drove this itself," replayed. Not live.
- **Pin seeds** where possible so a recorded run is reproducible if you need to re-capture.
- This is the **highest-risk P1 item** — spike it first (below), and never let it block the P0 spine.

## 9. Spike checklist (do this 30-min spike before building P1)

1. **Sanity-check the installed CLI** matches the verified flags: `claude -p "test" --output-format json | jq .result`; confirm `--permission-mode acceptEdits`, `--allowedTools "Read,Edit,Write"`, `--max-turns`, `--bare`, `--model` exist (`claude --help`; expect v2.1.x+).
2. Run `claude -p "add a one-line comment to train.py" --bare --permission-mode acceptEdits --allowedTools "Read,Edit"` in a throwaway git dir (as cwd) → confirm it edits the file non-interactively and you can read `git diff`.
3. Confirm the **turn cap + wall-clock timeout** actually bound it (kill behavior on a deliberately hard prompt).
4. Confirm a `git worktree`-based per-experiment workspace works and edits stay contained.
5. Decide editor model (`$KUN_EDITOR_MODEL`) — may be cheaper/faster than the planner model.
6. (If using Codex as fallback) sanity-check `codex exec "<prompt>" --sandbox workspace-write --ask-for-approval never`.

If the spike is shaky, P1 still degrades gracefully to `config-patch` — but the spike de-risks the single most uncertain piece of the build.
