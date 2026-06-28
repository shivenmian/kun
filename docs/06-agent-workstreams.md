# Kun Agent Workstreams

> **Reconciled with [`00-spec.md`](00-spec.md) (canonical; wins on conflict).** v4 deltas: the **LLM is the driver** via a **LiteLLM model id** (LiteLLM is IN — provider-agnostic planning + a minimal per-mission model picker, powering **model benchmarking**, P2); heuristic planner is fallback/baseline. Kun supports **both Mode A (Kun drives) and Mode B (Kun observes/steers an external loop)** plus a **Mode-B feedback channel** (`GET /missions/{id}/state`). The **code patcher** has two implementations: **`config-patch` (P0)** + **`agent-edit` (P1, orchestrates Claude Code/Codex to edit real model code)**. Ship the engine-agnostic **open logging contract + ~5-line `kun_log` emit helper** as a first-class deliverable (the wedge) — every producer is an equal citizen, and an **independent external loop emitting live** is a DoD. Emit `operator` (draft/debug/improve), `valid`/`buggy` statuses, `schema_version`, plus v4 events `instruction_added`/`experiment_approved`/`experiment_rejected` (doc 03). **Live fork execution, approval gate, mid-run instruct, and commit-per-node are core (P1).** **Research-memory panel + leaderboard + topbar status are CORE (P0)** frontend components; the node-view **`compare` view has moved P0→P1** (built first in P1 — pure cockpit craft, not cut); the **cross-model/benchmarking compare view stays P2**. **SQLite cut** (JSONL + in-memory only). Everything is tagged **P0/P1/P2** — build the P0 spine first, then P1 power features, then P2 benchmarking. **v5 deltas (no scope added, nothing deleted):** **craft-first** is the operating principle (concentrate P0 hours on the graph + research-memory panel + the closed constraint loop *firing visibly* — the only winnable moat in the timeframe); the node-view `compare` view moved P0→P1; **`agent-edit` is explicitly gated** on the doc-08 sanity spike (recorded-only, the top scope-trap / most-droppable P1 item); two independent time-safety valves — a **graceful drop-order** and an independent **`agent-edit` risk gate** (see build order below). Build order: contract + sample events + UI **before the trainer**. nanogpt can be a **recorded Kun-driven (Mode-A + `agent-edit`) run** (preferred), with an external-session→convert (Mode-B ingest) fallback; honesty + rich-trajectory requirements apply either way.

## Purpose

Because the team is one person using multiple coding agents, split the work into isolated tracks with clear contracts.

The most important shared contract is the event schema in `docs/03-event-schema.md`.

## Workstream A: Backend and event log

### Goal

Build the FastAPI backend, the engine-agnostic JSONL flight recorder + the open logging contract, the ~5-line emit helper (`kun_log`), and the mission state reducer. The contract is the wedge: any producer (Kun's loop in Mode A, an external agent in Mode B, a script, a human) is an equal citizen. Expose **two equal emit paths** (append to `$KUN_EVENTS` or POST to `/missions/{id}/ingest`) and the **Mode-B feedback channel** (`GET /missions/{id}/state`). The contract and state endpoint are engine-agnostic.

### Responsibilities

- FastAPI app setup.
- Pydantic event models — include `schema_version`, `operator` (draft/debug/improve), map `experiment_finished`→`valid` / `experiment_failed`→`buggy`, AND the v4 events `instruction_added` / `experiment_approved` / `experiment_rejected` (doc 03).
- Engine-agnostic open logging contract + ~5-line `kun_log(...)` emit helper, shipped as a documented deliverable (not internal-only).
- Storage is JSONL + in-memory state only. Do NOT add SQLite or any DB (cut for MVP per spec §3/§7).
- JSONL append/read.
- Mission directory structure under `runs/`.
- Event id/timestamp assignment.
- Mission state builder from events.
- HTTP endpoints for missions/events/state.
- `POST /missions/{id}/ingest` — second equal emit path (server fills the envelope; external producers POST the same dict).
- `GET /missions/{id}/state` — Mode-B feedback channel: returns active constraints + pending fork/instruct so an external loop can read steering back out.
- Steering endpoints: approve/reject/edit a pending proposal (emit `experiment_approved`/`experiment_rejected`), mid-run instruct (emit `instruction_added`), fork-from-node, stop/pause.
- SSE stream endpoint.

### Inputs

- Event schema doc.
- Mission spec shape.

### Outputs

- `backend/app/main.py`
- `backend/app/core/event_log.py`
- `backend/app/core/state_builder.py`
- `backend/app/api/missions.py` (incl. `/missions/{id}/ingest`, `/missions/{id}/state`, and steering: approve/reject/instruct/fork/stop)
- `backend/app/api/stream.py`
- tests or smoke scripts

### Acceptance criteria

- Can append and read events.
- Can stream events over SSE.
- Can rebuild mission state from a sample event log.
- An external producer can emit valid events via BOTH paths: appending to `$KUN_EVENTS` and POSTing to `/missions/{id}/ingest`; the UI renders a producer Kun did not run.
- `GET /missions/{id}/state` returns active constraints + pending fork/instruct (Mode-B feedback channel).
- Approval/instruct/fork actions emit `experiment_approved`/`experiment_rejected`/`instruction_added` and are reflected in rebuilt state.

## Workstream B: Tiny CNN live loop

### Goal

Build the reliable live demo path AND own the **code patcher** (one interface, two implementations).

### Responsibilities

- Fashion-MNIST CNN training script.
- Config file support.
- Metrics JSONL output.
- Experiment workspace creation.
- **Patcher interface — `config-patch` (P0):** writes changed keys into a per-experiment config file. Reliable, seconds/cycle; the always-available fallback that powers the tiny-CNN path.
- **Patcher interface — `agent-edit` (P1):** hand the proposed change to a **coding agent (Claude Code / Codex) run as a subprocess** to edit *real model code*, capture the resulting diff, emit `file_diff_created`. This is what lets Kun autoresearch any model (e.g., nanogpt), not just config knobs. Sandbox edits to the per-experiment workspace; expect minutes & nondeterminism (sequence per §11/§4 risk).
- **Runner subprocess:** execute the train/eval command on the patched workspace; parse the metric.
- **commit-per-node (P1):** optionally `git commit` each accepted node on a per-trajectory branch; store the sha (pairs with `agent-edit`).
- Metrics parsing.
- Basic evaluation.

### Inputs

- Mission spec.
- Event writer from Workstream A.

### Outputs

- `examples/tiny_cnn/train.py`
- `examples/tiny_cnn/config.yaml`
- `examples/tiny_cnn/mission.yaml`
- `backend/app/adapters/tiny_cnn.py`
- `backend/app/loop/patcher.py` (config-patch + agent-edit behind one interface)
- runner script

### Acceptance criteria

- Runs on CPU.
- Writes metrics.
- Kun can execute 3-5 experiments.
- Produces events for proposal, diff, metrics, result, evaluation.
- `config-patch` works on the tiny-CNN path (P0).
- `agent-edit` can drive a coding-agent subprocess to edit real code and return a diff (P1), at least on a fast target.

## Workstream C: Autoresearch planner/evaluator

### Goal

Implement proposal/evaluation/decision logic.

### Responsibilities

- LLM-driven planner (the driver): proposes hypothesis AND the actual change (params for `config-patch`; code edits for `agent-edit`), plus rationale and the post-run evaluation. Routed through **LiteLLM** so the provider/model is the mission's **LiteLLM model id** — keep the interface model-agnostic.
- **LiteLLM is IN (P2):** provider-agnostic planning + a **minimal per-mission model picker** (just pick a model id — NOT a settings UI, no temperature/test-connection chrome), powering **model benchmarking** (run the same mission under N models, compare them as autoresearchers — sample-efficiency, time/cost to target).
- Heuristic planner as fallback + baseline (runs on schema-validation failure and in no-key/offline demo mode); also a benchmark control (LLM-driver vs heuristic).
- Structured output validation.
- Evaluator verdicts.
- Decider next actions.
- Constraint handling. **P0:** the deterministic NaN→LR `bound` generator + the hard-reject filter (the hero spine). **P1 — research-memory enrichment ([doc 11](11-research-memory-design.md)):** a **two-tier** model (deterministic hard `bound`s + bias-only soft lessons), more deterministic learned rules (e.g. underfitting → `dropout` bound), positive Σ-summary lessons injected into the prompt, and memory hygiene (merge constraints + grow confidence). Reuse the canonical constraint object; keep the hard tier rule-derived (never let memory no-op); any LLM-authored memory is soft-tier/additive only.

### Inputs

- Current mission state.
- Previous experiments and metrics.
- Human constraints.

### Outputs

- `backend/app/loop/planner.py`
- `backend/app/loop/evaluator.py`
- `backend/app/loop/decider.py`
- `backend/app/loop/schemas.py`
- `backend/app/loop/llm_client.py` (LiteLLM wrapper; model id from mission spec)

### Acceptance criteria

- Loop works with the LLM driver when a LiteLLM model id + provider key is configured (LLM proposes hypothesis + the actual change + evaluation; emits `operator`).
- Loop degrades gracefully to the heuristic planner/baseline when no key is set or LLM JSON fails validation.
- Invalid LLM JSON falls back safely (schema validation + retry).
- (P2) The same mission can be run under ≥2 LiteLLM model ids for benchmarking.

## Workstream D: Frontend cockpit

### Goal

Build the main product UI.

### Responsibilities

- Vite React app.
- Event reducer.
- React Flow trajectory graph (nodes badged by `operator`, colored by `valid`/`buggy` status — buggy = red).
- Experiment detail panel.
- Metrics chart.
- Diff viewer (react-diff-viewer, not Monaco).
- Compare view (P1, built FIRST in P1): diff two nodes' configs + overlay their metric curves. (Moved out of P0 — pure cockpit craft, not cut. The `CompareView.tsx` file is still built, just in P1.)
- Research-memory panel (CORE): mission-wide accumulated constraints/learnings; a new learned constraint visibly enters it and reshapes the next proposal. **P1 enrichment ([doc 11](11-research-memory-design.md)):** also render positive Σ-summary lessons and rising confidence as evidence accumulates (the panel becomes a research notebook, not just a blocklist).
- Leaderboard (results table sorted by metric).
- Topbar status: mission name, best metric, current experiment, budget used, mode (**A-live / B-observe / replay / paused**), runtime, model.
- Event stream.
- Mission launcher (includes the minimal per-mission model picker — LiteLLM model id).
- Steering controls: fork dialog · **approval gate (approve / reject / edit a pending proposal, P1)** · **mid-run instruct box (P1)** · stop/pause.
- Cross-model / benchmarking compare view (P2): the same mission run under N models side-by-side, compared as autoresearchers.

### Inputs

- Sample event logs.
- Backend API.

### Outputs

- `web/src/components/TrajectoryGraph.tsx`
- `web/src/components/ExperimentDetails.tsx`
- `web/src/components/MetricsChart.tsx`
- `web/src/components/DiffViewer.tsx`
- `web/src/components/CompareView.tsx` (P1)
- `web/src/components/ResearchMemoryPanel.tsx`
- `web/src/components/Leaderboard.tsx`
- `web/src/components/TopbarStatus.tsx`
- `web/src/components/EventStream.tsx`
- `web/src/components/ForkDialog.tsx`
- `web/src/components/ApprovalGate.tsx`
- `web/src/components/InstructBox.tsx`
- `web/src/components/StopPauseControls.tsx`
- `web/src/components/BenchmarkCompareView.tsx` (P2)
- `web/src/state/eventReducer.ts`

### Acceptance criteria

- Can render static replay.
- Can subscribe to live SSE.
- Selecting a node updates detail panel.
- Fork UI can call backend.
- Approval gate can approve/reject/edit a pending proposal (calls backend; emits the v4 events).
- Instruct box injects NL guidance mid-run (`instruction_added`).
- (P2) Cross-model compare view ranks ≥2 models as autoresearchers.

## Workstream E: modded-nanogpt replay/import

### Goal

Create the serious credibility demo.

### Responsibilities

- **Prefer a recorded Kun-driven (Mode-A + `agent-edit`) run:** Kun's own loop edits real nanogpt training code overnight on GPU — *"Kun drove this itself."* **Fallback:** an EXTERNAL nanogpt session (Claude Code/Codex + markdown harness, Mode-B ingest) whose real artifacts are converted → events.jsonl via the open contract.
- Capture metrics/logs/diffs.
- Convert to Kun events (incl. `operator` + `schema_version`).
- Guarantee a rich trajectory: ≥1 real improvement, ≥1 real failure/NaN, a clear best/forkable node.
- Honesty guard: narrate exactly what happened — **Kun-driven (Mode A) vs ingested (Mode B)** — and never imply live execution that didn't occur.
- This is **Demo Beat 1** (the serious credibility run on real code). *(The wedge proof — a genuinely independent ~15-line external script emitting live — is the separate Beat 2 / DoD #4, owned via the contract.)*
- Ensure UI can render it.

### Inputs

- modded-nanogpt run artifacts.
- Event schema.

### Outputs

- `examples/replays/modded_nanogpt_demo.events.jsonl`
- optional converter script under `backend/scripts/convert_modded_nanogpt.py`
- notes on what each experiment represents

### Acceptance criteria

- Replay has enough nodes to feel serious.
- Contains successes/failures/constraints.
- Contains diffs and metrics.
- Can be forked visually.

## Workstream F: Demo polish

### Goal

Make the hackathon presentation reliable and impressive.

### Responsibilities

- Seeded demo data.
- One-click demo mission launch.
- Good default UI layout.
- Status badges and visual hierarchy.
- Backup replay.
- Demo script rehearsal.
- Screenshots/recording fallback.

### Outputs

- demo mode toggle or sample missions
- polished replay files
- final demo script

### Acceptance criteria

- Demo can run without manual fiddling.
- There is a fallback if live training fails.
- The product thesis is visible in the UI.

## Suggested parallelization order

> Respect the P0 → P1 → P2 gates (spec §9). UI before the trainer; ship the contract + emit helper + sample `events.jsonl` earliest so every other track builds against it.
>
> **Craft-first (operating principle, spec §7/§9):** for the demo the only winnable moat is **cockpit craft** — the graph, the research-memory panel, and the closed constraint loop *firing visibly* — so concentrate P0 hours there. The open-standard framing is nearly free structurally (`kun_log` ~5 lines + the Beat-2 producer ~15 lines) and does not trade against polish; the heavy P1/P2 machinery is what does, which is why it's gated.

### P0 — spine (start immediately; do these first)

1. Backend/event schema (+v4 deltas) + open logging contract + ~5-line `kun_log` emit helper (both paths: `$KUN_EVENTS` + `/missions/{id}/ingest`) + hand-authored rich sample `events.jsonl`.
2. Frontend static-replay cockpit on the sample (graph + node-view **triad: detail/diff/leaderboard** + research-memory panel + event stream + topbar). *(`compare` moved to P1 — see below.)*
3. Tiny CNN trainer + one-experiment runner (`config-patch`).
4. LLM-driven loop (Mode A) + budget/stop → `mission_finished` + the closed constraint loop (hero).
5. Live SSE + visual fork + replay.

### P1 — power features (start only after the P0 spine demos end-to-end)

6. **`compare` view** (moved P0→P1; build FIRST in P1) — diff two nodes' configs + overlay metric curves; pure cockpit craft, the most-wanted ML action.
6b. **Research-memory enrichment** ([doc 11](11-research-memory-design.md)) — two-tier memory (deterministic hard `bound`s + bias-only soft lessons); more deterministic learned rules (e.g. underfitting), positive Σ-summary lessons, memory hygiene (merge + confidence growth), and a gated soft-tier LLM "memory writer". Low-risk, high narrative value — build early in P1 (alongside `compare`); reuses the canonical constraint object (no schema change).
7. Live fork execution (Mode A) + approval gate + mid-run instruct.
8. **`agent-edit` patcher** (orchestrate Claude Code/Codex on real code) — **GATED:** build only after the doc-08 sanity spike passes; fall back to `config-patch` the instant a cycle flakes; it can't be demoed live (recorded-only) and is the top scope-trap / most-droppable P1 item.
9. Mode-B feedback channel (`GET /missions/{id}/state`) + commit-per-node.
10. Recorded Mode-A-on-real-code (nanogpt) run → serious replay.

### P2 — second demo story (start only after P1 hero steering works)

11. LiteLLM model picker + model benchmarking + cross-model compare view (`BenchmarkCompareView.tsx`; distinct from the P1 node-view `compare`).
12. Demo polish.
13. Desktop wrapper if time.

> Gates (spec §9): UI before the trainer. Do NOT start P1 until the P0 spine demos end-to-end; do NOT start P2 until P1's hero steering works.

**Two independent time-safety valves (spec §9 — don't conflate them):**

1. **Graceful drop-order** — when time runs low and everything built so far works, drop in **reverse build order, never touching P0**: **benchmarking (P2) → commit-per-node → Mode-B feedback channel → approval gate + mid-run instruct → recorded nanogpt run → `compare`.** A finished P0 + a clean slice of P1 beats a sprawl of half-built features.
2. **`agent-edit` risk gate** — *independent of how much time is left.* Build `agent-edit` only after the doc-08 sanity spike passes; if the spike fails or any later `agent-edit → train → eval` cycle flakes, fall back to `config-patch` immediately. It can't be demoed live (recorded-only) and is the top scope-trap, so it's often the first P1 item abandoned — expected, not a failure.

## Execution & integration (worktrees, ownership, merge order)

For a heavy parallel build, run each coding agent in its own **git worktree + branch off `main`** — isolation prevents collisions on shared files (e.g. the event schema) — and integrate to `main` **one branch at a time**. (Your own manual commits still go straight to `main` per this repo's convention; worktrees are just for parallel build agents.)

**Ownership boundaries** (map the workstreams above onto the real repo layout — `backend/` · `web/` · `kun/` · `examples/` · `scripts/`):

- **A** (backend / event log / contract): `backend/app/**`, `kun/log.py`
- **B** (tiny-CNN + patcher): `examples/tiny_cnn/**`, `backend/app/loop/patcher.py`, the runner
- **C** (planner / evaluator / decider): `backend/app/loop/{planner,evaluator,decider,llm_client,schemas}.py`
- **D** (cockpit UI): `web/**`
- **E** (replays / import): `examples/replays/**`, `scripts/{gen_sample_events,convert_nanogpt}.py`
- **F** (demo polish): demo scripts, README, styling — after D merges

**Collision rules:**

- Each agent lists the files it will touch before editing; don't edit another agent's files without coordination.
- Keep shared contracts stable: the event schema (doc 03), API endpoint names (doc 02), and sample-event file paths. Changing one is a coordinated, **schema-doc-first** change.
- Prefer additive changes over refactors while branches are open; no repo-wide auto-formatters from a feature branch; commit frequently; run that area's checks before merging.

**Integration order** (mirrors the P0 → P1 → P2 build order):

1. event schema + open contract + emit helper + hand-authored sample `events.jsonl` (E + A)
2. cockpit UI against the static replay — P0 node-view **triad: detail/diff/leaderboard** + graph + research-memory panel + topbar (D)
3. backend live event stream / SSE (A)
4. tiny-CNN loop + `config-patch` (B + C)
5. P1 begins: node-view **`compare` view** FIRST (D), then live SSE wiring + fork / approval gate / instruct (A + D)
6. `agent-edit` patcher (B) **[GATED — doc-08 spike; fall back to `config-patch` if it flakes]**, Mode-B feedback channel (A), commit-per-node
7. nanogpt convert/record → serious replay (E)
8. benchmarking + cross-model `BenchmarkCompareView` (C + D), then polish (F)

Rationale: the UI works against the static replay first; the backend then replaces static data with live events; the loop emits real events; heavy/credibility work and benchmarking come last. Don't merge multiple large branches blindly — one at a time, with that area's checks green.

## Agent prompt templates

### Backend agent prompt

```text
You are implementing Kun's FastAPI backend and JSONL event log. Follow docs/03-event-schema.md exactly (incl. `schema_version`, `operator` draft/debug/improve, `valid`/`buggy` status mapping, AND the v4 events `instruction_added`/`experiment_approved`/`experiment_rejected`). Treat the engine-agnostic open logging contract + a ~5-line `kun_log(...)` emit helper as first-class shipped deliverables — any external producer (Kun's own loop in Mode A, or an external agent in Mode B) must be able to emit valid events via TWO equal paths: append to `$KUN_EVENTS` or POST to `/missions/{id}/ingest` (the server fills the envelope). Build minimal endpoints for creating missions, appending/reading events, reconstructing mission state, streaming events via SSE, the **Mode-B feedback channel `GET /missions/{id}/state`** (active constraints + pending fork/instruct), and **steering** (approve/reject/edit proposal, mid-run instruct, fork, stop/pause). Storage is JSONL + in-memory only — no SQLite. Keep code simple and demo-ready. Do not implement UI. Do not change event semantics without updating docs.
```

### Tiny CNN agent prompt

```text
You are implementing Kun's live ML demo adapter AND the code patcher. Build a Fashion-MNIST tiny CNN training script that reads YAML config, trains quickly on CPU/GPU, and writes metrics.jsonl. Implement the **patcher behind one interface with two implementations: `config-patch` (P0)** — write changed keys into a per-experiment config — and **`agent-edit` (P1)** — hand the proposed change to a coding agent (Claude Code / Codex) run as a subprocess to edit real model code, capture the diff, emit `file_diff_created`. Then implement a backend runner/adapter that creates the per-experiment workspace, runs the train/eval command, parses metrics, and emits Kun events; optionally `git commit` each accepted node (commit-per-node, P1). `config-patch` is the always-available reliable fallback; prefer reliability over model sophistication.
```

### Frontend agent prompt

```text
You are implementing Kun's cockpit UI. Build a Vite React app with: React Flow trajectory graph (nodes badged by `operator`, colored by `valid`/`buggy` status), experiment details, metrics chart, diff viewer (react-diff-viewer), leaderboard, compare view (`CompareView.tsx` — diff two nodes + overlay curves, **P1**), research-memory panel (mission-wide accumulated constraints), topbar status (mode = A-live / B-observe / replay / paused), event stream, and **steering controls: fork dialog + approval gate (approve/reject/edit a pending proposal) + mid-run instruct box + stop/pause**. Craft-first: the P0 moat is the graph + research-memory panel + the closed constraint loop firing visibly — spend P0 hours there. **Research-memory is CORE (P0), not optional**; the node-view **`compare` view is P1 (build it FIRST in P1 — moved out of P0, not cut)**. Add a separate **cross-model / benchmarking compare view (`BenchmarkCompareView.tsx`, P2)** — the same mission under N models side-by-side, compared as autoresearchers. The UI is driven by Kun JSONL events and works with both static replay files and live SSE events. Keep the UI trajectory-first.
```

### modded-nanogpt agent prompt

```text
You are building Kun's modded-nanogpt serious-demo path (Beat 1). **Prefer a recorded Kun-driven run: Kun's own loop (Mode A + `agent-edit`) edits real nanogpt training code overnight on GPU** — "Kun drove this itself." **Fallback:** take real artifacts from an EXTERNAL nanogpt session (Claude Code/Codex + markdown harness, Mode-B ingest) and convert them into Kun events via the open contract (incl. `operator` + `schema_version`). Honesty guard: narrate exactly what happened — Kun-driven (Mode A) vs ingested (Mode B) — never imply live execution that didn't occur. The replay should tell a compelling research story with a rich trajectory: baseline, ≥1 improvement, ≥1 failure/NaN, learned constraints, throughput tradeoffs, and a clear forkable best branch.
```
