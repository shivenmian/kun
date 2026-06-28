# Kun

Kun is a mission-control **cockpit and runtime** for autonomous ML experiment loops — and the **open standard those trajectories are logged in**.

It is not a W&B replacement and it is not a generic agent chat UI. Kun is designed around a different primitive: the **research trajectory**. A trajectory captures why an autonomous researcher ran each experiment, what changed, what happened, what evidence came back, what the agent learned, and where a human can steer next.

Kun works in **two modes**: it can **drive** the loop itself (**Mode A** — its LLM planner proposes a change, a patcher applies it via config edits *or real code edits through a coding-agent subprocess*, the runner trains/evals, and it decides what to try next), or **observe and steer** an external loop (**Mode B** — any loop emits Kun's event format in ~5 lines via `kun_log`). Add-on, not a replacement: point Kun at your model, or plug your existing loop into the cockpit.

## Core thesis

Existing ML tooling is mostly **run-centric**: params, metrics, artifacts, curves, checkpoints.

Existing agent tooling is mostly **trace-centric**: prompts, model calls, tool calls, spans, latency, cost.

Autonomous ML experimentation needs a **trajectory-centric** interface:

```text
mission
  -> hypotheses
    -> code/config diffs
      -> experiments
        -> metrics/evals/failures
          -> decisions
            -> branches/forks/human interventions
```

## What Kun does (scope, by build priority)

**Core (P0)** — a complete demo on its own:
- Create a mission; run a live autonomous loop on a tiny task (LLM-driven, `config-patch`).
- Record everything as JSONL events via the open contract (`kun_log`); ingest any external loop in ~5 lines.
- Render a live, replayable **trajectory cockpit** (graph + node detail + diff + metrics + research-memory panel).
- The **closed constraint loop**: a failure → a learned constraint with a bound → the next proposal visibly respects it (the hero beat).

**Power (P1)** — raises the ceiling:
- `agent-edit`: Kun drives autoresearch on **real model code** (not just config knobs) via a coding-agent subprocess.
- Live steering: **fork-from-node, approval gate, mid-run instruct** — all executing in Mode A; commit-per-node.
- **Research-memory enrichment** (two-tier memory: deterministic hard bounds + bias-only soft lessons; positive Σ-summaries; confidence growth) — see [`docs/11-research-memory-design.md`](docs/11-research-memory-design.md).

**Second story (P2):** model benchmarking — run the same mission under different models and compare them *as autoresearchers*.

Build P0 first; see [`docs/00-spec.md`](docs/00-spec.md) §7/§9 for the full P0/P1/P2 order and the "minimum strong demo" stop-point.

## Recommended MVP stack

```text
Frontend: Vite React
UI: Tailwind + shadcn/ui
Graph: React Flow
Charts: Recharts
Diff viewer: react-diff-viewer (not Monaco)
Backend: FastAPI
Event stream: Server-Sent Events first, WebSocket only if needed
Storage: JSONL event log only (in-memory state builder; no SQLite for MVP)
Agent provider: LiteLLM (provider-agnostic) + a minimal per-mission model picker (powers benchmarking; no elaborate settings UI)
Live task: Fashion-MNIST tiny CNN
Serious replay: modded-nanogpt recorded trajectory
```

## Development (local)

Two processes — FastAPI backend and the Vite cockpit.

```bash
# 1) Backend (FastAPI + SSE on :8000)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 2) Cockpit (Vite + React on :5173, proxies /api -> :8000)
cd web
npm install
npm run dev
```

Then open the cockpit and load the bundled replay
`examples/replays/sample.events.jsonl` (the static replay renders with no backend
running). For a live tiny-CNN mission, set `ANTHROPIC_API_KEY` in `backend/.env`
(the loop falls back to a heuristic planner with no key). The wedge proof:

```bash
KUN_EVENTS=runs/mission_external_demo/events.jsonl python examples/external_loop_demo.py
# then "Observe external mission" -> mission_external_demo in the cockpit (or curl POST /missions/register)
```

The event log is the single source of truth: every mission lives at
`runs/<mission_id>/events.jsonl`; live and replay consume the same bytes.

## Documentation map

- [`docs/00-spec.md`](docs/00-spec.md) - **canonical post-audit build spec. Read this first; it wins over docs 01–07 where they conflict.**
- [`docs/01-product-design.md`](docs/01-product-design.md) - product thesis, scope, UX, features, non-goals.
- [`docs/02-technical-architecture.md`](docs/02-technical-architecture.md) - system architecture and implementation shape.
- [`docs/03-event-schema.md`](docs/03-event-schema.md) - JSONL event contract and examples.
- [`docs/04-implementation-plan.md`](docs/04-implementation-plan.md) - build order, milestones, and acceptance criteria.
- [`docs/05-demo-plan.md`](docs/05-demo-plan.md) - final demo strategy and script.
- [`docs/06-agent-workstreams.md`](docs/06-agent-workstreams.md) - parallel coding-agent tasks.
- [`docs/07-modded-nanogpt-runbook.md`](docs/07-modded-nanogpt-runbook.md) - plan for the serious recorded run.
- [`docs/08-agent-edit-design.md`](docs/08-agent-edit-design.md) - design note for the `agent-edit` patcher (Kun driving real code via a coding-agent subprocess). Read before P1.
- [`docs/09-operator-checklist.md`](docs/09-operator-checklist.md) - human/ops tasks outside the build (API keys, GPU, the Asset B nanogpt run, demo prep).
- [`docs/10-implementation-handoff.md`](docs/10-implementation-handoff.md) - kickoff brief for the implementation agent (paste it, or point the agent at it).
- [`docs/11-research-memory-design.md`](docs/11-research-memory-design.md) - design note for the P1 research-memory enrichment (two-tier memory: hard bounds + soft lessons). Read before building P1 memory.
