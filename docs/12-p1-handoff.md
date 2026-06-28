# Kun — P1 Implementation Handoff (subagent-orchestrated)

Kickoff brief for the **P1 lead orchestrator**. P1 is built the way P0 was: **the lead does NOT
write everything — it ORCHESTRATES parallel subagents** (each in its own git worktree + branch
off `main`, owning a disjoint path set), with short serial scaffold/contract-freeze before, and
serial integration (merge one branch at a time) after. Paste the prompt below into a fresh agent,
or point the agent at this file. (Human/ops tasks — GPU, the Asset B nanogpt run, the `agent-edit`
spike machine, demo prep — live in [`09-operator-checklist.md`](09-operator-checklist.md).)

**P0 is complete, verified, and integrated on `main`.** This is P1 — the power features that make
Kun a cockpit, not a viewer.

---

## Carried forward from P0 (track these — they are NOT new P1 features)

- **Stop / pause control.** Spec §4 tags *"Stop / pause (P0)"*, but it was outside the P0 build
  scope that shipped — only the **automatic** budget/stop → `mission_finished` is built. The
  **human** stop/pause control (button + endpoint) is unbuilt and is **absorbed into the P1 live
  steering work** (Round 2 below). Build `StopPauseControls.tsx` + `POST /missions/{id}/stop`
  (or pause) there.
- **Minor non-blocking P0 nits (fix opportunistically, not gating):** `/stream` 404s if a client
  connects *before* the events file exists (produce-then-observe avoids it — harden the tailer to
  wait for the file); and a cosmetic `bestExperiment` (backend `/experiments`) vs `bestExperimentId`
  (web reducer) naming divergence in the path the cockpit doesn't consume.

---

## The prompt

```text
You are the LEAD ORCHESTRATOR for Kun's P1 build. Kun is a mission-control cockpit + runtime
for autonomous ML experiment loops, organized around the "research trajectory" primitive. P0
is COMPLETE, verified, and integrated on `main`. Your job is P1 — the power features that make
it a cockpit, not a viewer — and you BUILD IT BY ORCHESTRATING PARALLEL SUBAGENTS, not by
writing everything yourself. Mirror the P0 build: short serial scaffold + contract-freeze ->
fan out parallel subagents in worktrees -> serial integration (one branch at a time).

Working dir: /Users/shivenmian/kun  (git repo; manual commits live on `main`).

## READ FIRST (source of truth, in order)
- docs/00-spec.md — CANONICAL (wins on any conflict). Focus §4 (loop/steering/closed
  constraint loop), §6 (cockpit surfaces), §7 (P1 scope), §8 (demo beats — esp. Beat 1 & 4),
  §9 (build order + the TWO time-safety valves + the agent-edit risk gate), §10 (DoD).
- CONTRACT.md — the FROZEN cross-component contract (envelope, event types, §3 constraint
  object + the two memory tiers, §5 HTTP surface incl. the RESERVED P1 endpoints, §6
  ownership, §8 file-tail decision). Do NOT change the schema, endpoint names, or sample
  path unilaterally — YOU (the lead) own contract changes; subagents never touch it.
- docs/03-event-schema.md — full event examples (incl. the reserved v4 events).
- docs/06-agent-workstreams.md — workstreams, the P1 list, ownership boundaries, collision
  rules, and "Execution & integration" (worktrees, merge order).
- docs/08-agent-edit-design.md — READ BEFORE building agent-edit (it's gated on this spike).
- docs/11-research-memory-design.md — the research-memory enrichment design (two-tier memory).
- docs/12-p1-handoff.md — this brief (incl. the "Carried forward from P0" section).

## GROUND RULES (carry over from P0 — non-negotiable; bind every subagent)
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
  (GET /missions/{id}/state, steering, stop) are already RESERVED — you (the lead) add their
  payloads to doc 03 + CONTRACT first (schema-doc-first) in Phase 0, THEN subagents implement.

## ORCHESTRATION — USE SUBAGENTS (primary mode; do NOT build it all yourself)
Prefer parallel subagents wherever paths are disjoint; only work inline for the serial glue
(contract freeze, the spike, integration, gates). Subagents run in their OWN git worktree +
branch off `main` and own a DISJOINT path domain (never cross):
  - API   -> backend/app/api/** , backend/app/events/** , backend/app/state/**
  - LOOP  -> backend/app/loop/**
  - WEB   -> web/**
  - DATA  -> examples/replays/** , scripts/**   (nanogpt)

Phase 0 — SERIAL (you), before any fan-out:
  1. Verify the P0 baseline runs (see VERIFY section).
  2. Run the agent-edit spike NOW (doc 08 §9) — its pass/fail gates whether the agent-edit
     track ever launches.
  3. FREEZE the P1 contract additions schema-doc-first: add payloads for the reserved P1
     events + the P1 endpoint shapes (GET /missions/{id}/state, steering, POST
     /missions/{id}/stop) into CONTRACT.md + docs/03, keeping §0/§5 names stable. This is
     what makes parallel subagents safe (it's what CONTRACT.md was for P0).
  4. Post your plan (worktree layout, Round-1 subagent briefs with EXACT owned paths,
     integration order) and confirm before fanning out.

Then fan out parallel subagents PER ROUND, integrating one branch at a time between rounds:

  Round 1 (parallel — mostly disjoint, highest value, lowest risk):
   - WEB subagent: compare view (web/src/components/CompareView.tsx + a node-view tab,
     overlay metric curves) AND render the enriched memory panel (positive lessons + rising
     confidence).
   - LOOP subagent: research-memory enrichment (doc 11 FIRST SLICE — the deterministic
     underfitting->dropout bound generator + memory hygiene merge/confidence; THEN positive
     Σ-summary soft lessons injected into the planner prompt). Unit-test each generator.
   - DATA subagent: kick off the nanogpt external-session hedge -> convert to a replay (Asset
     B fallback; recorded + timing-flexible, so start it early as insurance).

  Round 2 (parallel — live steering, full-stack; depends on the Phase-0 contract freeze):
   - API subagent: steering endpoints (approve/reject/edit a pending proposal; mid-run
     instruct; stop/pause; trigger fork-execute) + GET /missions/{id}/state (Mode-B feedback
     channel).
   - LOOP subagent: planner/runner read approvals + instructions + active constraints; LIVE
     fork EXECUTION (P0 fork is record-only); stop/pause honored mid-run.
   - WEB subagent: ApprovalGate.tsx, InstructBox.tsx, StopPauseControls.tsx (Stop/Pause is
     the CARRIED-FORWARD P0 item), and wire the fork dialog to actually execute.

  Round 3 (gated / heavier — parallel where possible):
   - LOOP subagent: agent-edit patcher — ONLY if the Phase-0 spike passed; fall back to
     config-patch the instant a cycle flakes. Recorded-only; top scope-trap / most droppable.
   - DATA subagent: finalize the serious nanogpt replay (prefer Kun-driven Mode-A+agent-edit
     if the spike holds; else the converted external run). Honesty guard: narrate exactly
     what produced it; never imply live execution that didn't occur.

  Every subagent: own ONLY its domain's paths; LIST files before editing; never touch another
  domain's paths or the frozen contract; the loop emits events ONLY via kun_log; TEST/run its
  deliverable (not just write it); report back. You (lead) merge one branch at a time, own
  integration + the contract, and run the capstone checks each round.

GATES (spec §9): do NOT start P2 (benchmarking) until P1 hero steering works. Two time-safety
valves: (a) graceful drop-order — under time pressure drop in reverse build order, never
touching P0; (b) the agent-edit risk gate — independent of time, drop to config-patch the
moment a cycle flakes.

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

## KNOWN GOTCHAS FROM P0 (carry forward; tell each subagent)
- LiteLLM + new Claude models: do NOT send `temperature` (claude-opus-4-8 rejects it; litellm
  can't drop it). Already handled in llm_client.py — keep it that way for any new LLM calls.
- SSE frames are NAMED `kun`; the web client listens via addEventListener("kun") — match this
  for any new stream consumers.
- The tiny-CNN accuracy curve is genuinely flat; the rich arc lives in the sample replay. Keep
  demos honest. The decider promotes the current-best node (baseline included).
- ANTHROPIC_API_KEY is in backend/.env (LLM path); the loop falls back to heuristic with no key.

## CARRIED FORWARD FROM P0 (not new features — see docs/12 top section)
- Human Stop/Pause control (spec §4 P0; only auto budget/stop shipped) -> build in Round 2.
- Minor: harden /stream to tolerate a not-yet-existing events file; bestExperiment naming nit.

## VERIFY THE P0 BASELINE FIRST (before fanning out)
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

Start with Phase 0 (verify P0, run the agent-edit spike, FREEZE the P1 contract additions,
post your plan), then fan out Round 1 subagents. Prioritize parallel subagents wherever paths
are disjoint. Do NOT start P2. You own the contract and integration.
```
