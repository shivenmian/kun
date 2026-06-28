# Kun — Implementation Handoff

This is the kickoff brief for the **implementation agent**. Either paste it into a fresh Claude Code
agent working in this repo, or point the agent straight at this file. (Human/ops tasks that are *not*
the build — API keys, GPU, the Asset B nanogpt run, demo prep — live in [`09-operator-checklist.md`](09-operator-checklist.md), not here.)

---

You are implementing Kun, a hackathon MVP, in this repo. Kun is a mission-control cockpit + runtime
for autonomous ML experiment loops, organized around the "research trajectory" primitive.

**Read first, treat as source of truth (in this order):**
- `docs/00-spec.md` — **CANONICAL.** It wins over every other doc on any conflict. Read it fully.
- `docs/03-event-schema.md` — the event contract every component builds against.
- `docs/02-technical-architecture.md` — architecture, ProjectAdapter, API surface, frontend state.
- `docs/08-agent-edit-design.md` — read before starting P1 (the `agent-edit` patcher).
- `docs/06-agent-workstreams.md` — workstream contracts + "Execution & integration" (worktrees, ownership, merge order).
- `docs/01, 04, 05, 07` for product/plan/demo/runbook detail. `docs/09` is the human ops checklist (not your job).

**Non-negotiables:**
- The JSONL event log is the **single source of truth**. Live mode and replay mode consume the same
  events; UI state is derived from events and must be reconstructable from them. JSONL only — **no SQLite**.
- Build **UI before the trainer**. The cockpit + the open logging contract are the deliverable; the
  trainer just prints metrics.
- Build strictly in priority order with the gates (spec §7/§9): finish the **P0 spine end-to-end
  before starting P1**; finish **P1 hero steering before P2**. If time compresses, the P0 spine alone
  is the "minimum strong demo" — ship that.
- **Craft-first (spec §7).** For the demo, the only winnable moat is cockpit craft — the graph, the
  research-memory panel, and the closed constraint loop *firing visibly*. Spend P0 hours there. The
  open-standard framing stays the long-term story and is near-free (`kun_log` + the Beat-2 producer);
  the heavy P1/P2 machinery is what trades against polish. Note **`compare` is P1, not P0** (P0 node-view = detail/diff/leaderboard triad).
- **Two time-safety valves (spec §9), don't conflate them:** (1) *graceful drop-order* (out of time,
  everything works) drops in reverse build order — benchmarking (P2) → commit-per-node → Mode-B feedback
  channel → approval gate + instruct → recorded nanogpt → `compare` — never P0; (2) the **`agent-edit`
  risk gate** is independent of time: build it only after the doc-08 spike passes, fall back to
  `config-patch` the instant a cycle flakes. `agent-edit` can't be demoed live and is the top scope-trap.
- Every task must serve a demo beat (spec §8). Don't overbuild. Respect the non-goals (spec §13):
  no SQLite, no full GitHub PR integration, no MCTS, no desktop wrapper, no elaborate LLM settings UI.
- Don't fake the nanogpt run; honor the honesty guard (spec §8 / doc 07).

**Already exists — do NOT recreate; build against these:**
- `kun/log.py` — the ~5-line open-contract emit helper (`kun_log`).
- `examples/replays/sample.events.jsonl` — the rich sample trajectory (Asset A). The cockpit must
  render THIS first. (Regenerate via `scripts/gen_sample_events.py`.)
- `examples/external_loop_demo.py` — the independent-producer wedge proof (Asset C).
- `scripts/convert_nanogpt.py` — converter scaffold for the serious run (Asset B; real data comes later).

**Build into this layout:** `backend/` (FastAPI), `web/` (Vite React + TS), `examples/tiny_cnn/`.
**Stack:** spec §3 / README (Vite React + React Flow + Recharts + react-diff-viewer; FastAPI + SSE;
JSONL only; LiteLLM for provider-agnostic planning).

**First task (P0, in order — do not jump ahead):**
1. Scaffold `backend/` + `web/` so both run locally with one/two commands; document them in README.
2. Render `examples/replays/sample.events.jsonl` in the cockpit as a static replay:
   React Flow trajectory graph (nodes badged by operator, colored by valid/buggy) → click a node →
   detail panel (hypothesis/rationale/changes/diff/metrics/verdict) + metrics chart + diff viewer
   (react-diff-viewer) + event stream + the **research-memory panel** (mission-wide accumulated
   constraints). This static replay is the first success criterion — prove the core product visual
   before any backend/live/trainer work.

Then continue down the P0 spine in spec §9 (backend event log + SSE → tiny-CNN loop with `config-patch`
+ the closed constraint loop → live SSE + visual fork + replay).

**Acceptance:** spec §10 (Definition of done). For the first milestone specifically: loading the sample
events file shows a populated trajectory graph, and clicking a node shows hypothesis/diff/metrics/
verdict, with the research-memory panel showing the learned constraint and the proposal that respects it.

**If running multiple parallel agents:** follow `docs/06` "Execution & integration" — one git worktree +
branch per agent off `main`, the file-ownership boundaries listed there, collision rules (list files
before editing; keep the event schema / API names / sample paths stable), and integrate to `main` one
branch at a time in the stated order.

Start by reading `docs/00-spec.md` and `docs/03-event-schema.md`, then scaffold and make the sample
replay render. Do not beautify the UI before it renders the trajectory.
