# Kun — P1 Implementation Handoff

Kickoff brief for the **P1 implementation agent**. Paste the prompt below into a fresh agent in
this repo, or point the agent at this file. (Human/ops tasks — GPU, the Asset B nanogpt run, the
`agent-edit` spike, demo prep — live in [`09-operator-checklist.md`](09-operator-checklist.md).)

**P0 is complete, verified, and integrated on `main`.** This is P1 — the power features that make
Kun a cockpit, not a viewer.

---

## Carried forward from P0 (track these — they are NOT new P1 features)

- **Stop / pause control.** Spec §4 tags *"Stop / pause (P0)"*, but it was outside the P0 build
  scope that shipped — only the **automatic** budget/stop → `mission_finished` is built. The
  **human** stop/pause control (button + endpoint) is unbuilt and is **absorbed into the P1 live
  steering work** (item 3 below). Build `StopPauseControls.tsx` + a `POST /missions/{id}/stop`
  (or pause) there.
- **Minor non-blocking P0 nits (fix opportunistically, not gating):** `/stream` 404s if a client
  connects *before* the events file exists (produce-then-observe avoids it — harden the tailer to
  wait for the file); and a cosmetic `bestExperiment` (backend `/experiments`) vs `bestExperimentId`
  (web reducer) naming divergence in the path the cockpit doesn't consume.

---

## The prompt

```text
You are the implementation agent for Kun's P1 build. Kun is a mission-control cockpit +
runtime for autonomous ML experiment loops, organized around the "research trajectory"
primitive. P0 is COMPLETE, verified, and integrated on `main`. Your job is P1 — the power
features that make it a cockpit, not a viewer.

Working dir: /Users/shivenmian/kun  (git repo; manual commits live on `main`).

## READ FIRST (source of truth, in order)
- docs/00-spec.md — CANONICAL (wins on any conflict). Focus §4 (loop/steering/closed
  constraint loop), §6 (cockpit surfaces), §7 (P1 scope), §8 (demo beats — esp. Beat 1 & 4),
  §9 (build order + the TWO time-safety valves + the agent-edit risk gate), §10 (DoD).
- CONTRACT.md — the FROZEN cross-component contract (envelope, event types, §3 constraint
  object + the two memory tiers, §5 HTTP surface incl. the RESERVED P1 endpoints, §6
  ownership, §8 file-tail decision). Do NOT change the schema, endpoint names, or sample
  path unilaterally — route any change through the lead (schema-doc-first).
- docs/03-event-schema.md — full event examples (incl. the reserved v4 events).
- docs/06-agent-workstreams.md — workstreams, the P1 list, ownership boundaries, collision
  rules, and "Execution & integration" (worktrees, merge order).
- docs/08-agent-edit-design.md — READ BEFORE building agent-edit (it's gated on this spike).
- docs/11-research-memory-design.md — the research-memory enrichment design (two-tier memory).

## GROUND RULES (carry over from P0 — non-negotiable)
- JSONL event log is the single source of truth; in-memory state builder. NO SQLite.
- Live mode and replay consume the SAME event shape / same code path.
- The LLM is the DRIVER (LiteLLM). Heuristic planner is the no-key fallback only.
- The loop emits ONLY via kun_log(..., path=runs/<id>/events.jsonl) — it NEVER imports the
  API layer. Backend appends via the events module / kun_log too.
- The closed constraint loop's HARD tier stays deterministic and cannot no-op. Any
  LLM-authored memory is SOFT-tier (prompt bias) only (CONTRACT §3 / doc 11).
- Keep the state builders (backend AND web reducer) tolerant of unknown event types.
- Frozen: event schema (doc 03), §5 endpoint names, the sample path, kun/log.py. The P1
  events (instruction_added, experiment_approved, experiment_rejected) and endpoints
  (GET /missions/{id}/state, steering) are already RESERVED — adding them follows the
  contract; add their payloads to doc 03 + CONTRACT first (schema-doc-first), coordinated
  with the lead, then implement.

## WHAT ALREADY EXISTS (extend, don't recreate)
- Backend: backend/app/api/{routes.py, loop_hook.py}, backend/app/events/{models,log_io}.py,
  backend/app/state/builder.py. Endpoints live: POST /missions, /missions/{id}/start,
  GET /missions/{id}/{events,experiments,stream}, POST /missions/{id}/fork,
  POST /missions/register, GET /missions, GET /health. SSE is file-tail and yields NAMED
  `kun` frames + a `ready` marker.
- Loop: backend/app/loop/{planner,evaluator,decider,patcher,runner,constraints,llm_client,
  schemas,run_mission}.py (+ test_constraints.py). config-patch only. run_mission is the
  Mode-A loop, spawned as a subprocess by /start (idempotent lifecycle; recovers spec from
  the log).
- Web: web/src/components/{TrajectoryGraph,ExperimentDetails,DiffViewer,Leaderboard,
  MetricsChart,ResearchMemoryPanel,EventStream,TopbarStatus,ForkDialog,MissionLauncher,
  ui/primitives}.tsx, web/src/state/eventReducer.ts, web/src/lib/{api,status,utils}.ts.
  Vite proxies /api -> :8000. Deep-links: ?replay, ?live=<id>, ?observe=<id>.
- Examples: examples/tiny_cnn/* (train.py, config.yaml, mission.yaml), examples/external_loop_demo.py,
  examples/replays/sample.events.jsonl.

## P1 SCOPE & BUILD ORDER (spec §7/§9; do NOT reorder past the gates)
1. compare view — build FIRST. web/src/components/CompareView.tsx: diff two nodes' configs +
   overlay their metric curves. Pure cockpit craft. (Owns web/**.)
2. research-memory enrichment (doc 11) — START with the deterministic underfitting->`dropout`
   bound generator + memory hygiene (merge constraints + grow confidence). Then positive
   Σ-summary soft lessons injected into the planner prompt. Contained to
   backend/app/loop/{constraints,run_mission}.py (+ panel rendering in web). Keep the hard
   tier deterministic + unit-tested; LLM memory soft-tier only.
3. Live steering (Mode A — executes because Kun owns the loop):
   - Live fork EXECUTION (the P0 fork is record-only; now run the forked branch).
   - Approval gate: pause-on-proposal; approve/reject/edit before it runs
     (emit experiment_approved / experiment_rejected). Component: ApprovalGate.tsx.
   - Mid-run instruct: inject NL guidance that biases the next proposal
     (emit instruction_added). Component: InstructBox.tsx.
   - Stop / pause (CARRIED FORWARD FROM P0 — spec §4 tags it P0 but only auto budget/stop
     shipped). Build StopPauseControls.tsx + POST /missions/{id}/stop (pause/resume).
   Needs new backend steering endpoints + the planner reading approvals/instructions.
4. agent-edit patcher — GATED. Build ONLY after the doc-08 sanity spike passes; fall back to
   config-patch the instant a cycle flakes. Hand a proposed change to a coding-agent
   subprocess (Claude Code/Codex) to edit REAL model code, capture the diff, emit
   file_diff_created. Recorded-only (can't be demoed live). Top scope-trap — most droppable.
5. Mode-B feedback channel: GET /missions/{id}/state (active constraints + pending
   fork/instruct) so an external loop reads steering back out. + commit-per-node (optional).
6. Recorded Mode-A-on-real-code (nanogpt) run -> serious replay (Beat 1). Prefer a recorded
   Kun-driven (Mode-A + agent-edit) run; fallback = external session converted via Mode-B
   ingest. Honesty guard: narrate exactly what happened. See docs/07-modded-nanogpt-runbook.md
   and scripts/convert_nanogpt.py.

GATES (spec §9): do NOT start P2 (benchmarking) until P1 hero steering works. Two time-safety
valves: (a) graceful drop-order — under time pressure drop in reverse build order, never
touching P0; (b) the agent-edit risk gate — independent of time, drop to config-patch the
moment a cycle flakes.

## KNOWN GOTCHAS FROM P0 (carry forward)
- LiteLLM + new Claude models: do NOT send `temperature` (claude-opus-4-8 rejects it; litellm
  can't drop it). Already handled in llm_client.py — keep it that way for any new LLM calls.
- SSE frames are NAMED `kun`; the web client listens via addEventListener("kun") — match this
  for any new stream consumers.
- The tiny-CNN accuracy curve is genuinely flat; the rich arc lives in the sample replay. Keep
  demos honest. The decider promotes the current-best node (baseline included).
- ANTHROPIC_API_KEY is in backend/.env (LLM path); the loop falls back to heuristic with no key.

## CARRIED FORWARD FROM P0 (not new features — see this doc's top section)
- Human Stop/Pause control (spec §4 P0; only auto budget/stop shipped) -> build in item 3.
- Minor: harden /stream to tolerate a not-yet-existing events file; bestExperiment naming nit.

## PARALLELIZATION (optional — mirror P0)
Each agent in its own git worktree + branch off `main`, disjoint paths, integrate one branch
at a time (docs/06 "Execution & integration"). Early P1 parallelizes cleanly: compare view
(web/**) ∥ memory enrichment (backend/app/loop/**). Then steering (backend api + web), then
agent-edit (loop), then nanogpt (examples/replays + scripts). List files before editing; never
touch another agent's paths or the frozen contract. Every agent TESTS its deliverable (runs it).

## VERIFY THE P0 BASELINE FIRST (before extending)
- Backend: cd backend && source .venv/bin/activate && uvicorn app.main:app --port 8000
- Web: cd web && npm install && npm run dev  (open ?replay — the sample must render)
- A live mission: POST /missions then /missions/{id}/start; open ?live=<id> — graph grows live.
- Loop tests: python backend/app/loop/test_constraints.py (5/5).

## P1 DEFINITION OF DONE (spec §10, P1 rows)
- compare view ranks/overlays two nodes (DoD #2's P1 add).
- A user forks/instructs/approves/stops on a LIVE mission and it EXECUTES (Mode A); constraints
  deterministically reshape the next proposal (DoD #5 live-exec).
- agent-edit drives real-code autoresearch on >=1 model (recorded is fine) (DoD #6).
- The serious nanogpt run shows a rich real trajectory: >=1 improvement, >=1 failure/NaN, a
  clear best/forkable node (DoD #7), with the honesty guard.
- Research memory is richer: a LIVE run surfaces >=2 learned constraints (incl. a non-NaN
  one) and confidence sharpens (doc 11).

Start by reading spec §7/§9, CONTRACT.md, and doc 06's P1 list + integration order. Build the
compare view first, then the memory-enrichment first slice (underfitting bound + hygiene).
Do NOT start P2. Route any schema/endpoint/contract change through the lead.
```
