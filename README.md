# Kun

Kun is a mission-control **cockpit and runtime** for autonomous ML experiment loops — and the **open standard those trajectories are logged in**.

It is not a W&B replacement and it is not a generic agent chat UI. Kun is designed around a different primitive: the **research trajectory** — why an autonomous researcher ran each experiment, what changed, what happened, what evidence came back, what it learned, and where a human can steer next.

Kun works in **two modes**:
- **Mode A — Kun drives.** Its LLM planner proposes a change, a patcher applies it (config edits *or real code edits via a coding-agent subprocess*), the runner trains/evals, and it decides what to try next. Steering has teeth: fork, approve/reject, and mid-run instruct all execute.
- **Mode B — Kun observes/steers an external loop.** Any loop emits Kun's event format in ~5 lines via `kun_log`, and (optionally) reads Kun's steering back through a feedback channel. Add-on, not a replacement.

## Core thesis

Run-centric tools (W&B/MLflow) show **params, metrics, artifacts, curves**. Agent-tracing tools (LangSmith/Weave) show **prompts, calls, spans, cost**. Autonomous ML experimentation needs a **trajectory-centric** interface:

```text
mission
  -> hypotheses
    -> code/config diffs
      -> experiments
        -> metrics/evals/failures
          -> decisions
            -> branches/forks/human interventions
```

The wedge/moat is **ecosystem position**, won the way LangSmith/OpenTelemetry won observability: be the thing you *instrument your existing loop with* (Mode B) and *run your research on* (Mode A) — not a novel algorithm.

## Status

**P0 — core spine · ✅ built & tested.**
- LLM-driven autonomous loop (Mode A) on a tiny Fashion-MNIST CNN (`config-patch`); heuristic fallback with no key.
- Open logging contract + `kun_log` emit helper; JSONL event log is the single source of truth; in-memory state builder; live (SSE) and replay share one path.
- Live, replayable **trajectory cockpit**: React Flow graph + node-view (detail / diff / leaderboard) + research-memory panel + event stream + topbar instruments.
- The **closed constraint loop** (the hero): a failure → a learned constraint with a machine-checkable `bound` → the planner deterministically hard-rejects violating proposals → the next proposal visibly respects it.
- Budget/stop → `mission_finished`; visual fork.

**P1 — power features · ✅ built & tested.**
- **`agent-edit`** patcher: Kun drives autoresearch on **real model code** via a coding-agent (Claude Code/Codex) subprocess, with graceful fallback to `config-patch`.
- **Live steering**: approval gate (approve / edit / reject-with-replacement), mid-run instruct, fork-from-node that executes, stop/pause/resume — plus commit-per-node.
- **Mode-B feedback channel** (`GET /missions/{id}/state`): an external loop reads back constraints/instructions and obeys — the wedge *with teeth*.
- **Two-tier research memory**: deterministic **hard bounds** + bias-only **soft lessons** (positive Σ-summaries), with confidence growth. See [`docs/11-research-memory-design.md`](docs/11-research-memory-design.md).
- **Compare view**: diff two nodes' configs + overlay their metric curves.
- **Mission control UI**: persistent shell, mission navigator + history, new-mission modal, replay gallery (auto-discovered from `examples/replays/`), observe modal, control deck, topbar approval toggle, alerts/toasts.

**P2 — model benchmarking · ⬜ designed, not yet built.** Run the same mission under different models and compare them *as autoresearchers* (sample-efficiency, time-to-target). The backend is provider-agnostic (LiteLLM, per-mission model) so this is additive.

Canonical scope/priorities: [`docs/00-spec.md`](docs/00-spec.md). Frozen cross-component interface: [`CONTRACT.md`](CONTRACT.md).

## Stack

```text
Frontend   Vite + React + TS, Tailwind, React Flow (graph), Recharts, react-diff-viewer (not Monaco)
Backend    FastAPI + SSE; JSONL event log only (in-memory state builder; no SQLite)
Provider   LiteLLM (provider-agnostic) + per-mission model id; reads ANTHROPIC_API_KEY from backend/.env
Live task  Fashion-MNIST tiny CNN (config-patch); agent-edit drives real code via a coding-agent subprocess
```

## Run it (local)

Two processes — FastAPI backend and the Vite cockpit.

```bash
# 1) Backend (FastAPI + SSE on :8000)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 2) Cockpit (Vite + React on :5173, proxies /api -> :8000)
cd web && npm install && npm run dev
```

- **Static replay (no backend):** open the cockpit → **Replay** → "Fashion-MNIST sample".
- **Live tiny-CNN mission:** set `ANTHROPIC_API_KEY` in `backend/.env` (no key → heuristic planner), then **+ New mission** → "Create & start". Steer it from the Control Deck (approve/edit/reject, instruct, fork, pause/stop).
- **The wedge (Mode B), ~5 lines:**
  ```bash
  python examples/external_loop_demo.py        # someone else's loop; the only Kun bit is kun_log(...)
  # then: cockpit -> Observe -> mission_external_demo  (it appears live in the cockpit)
  ```

Every mission lives at `runs/<mission_id>/events.jsonl`; live and replay consume the same bytes.

## Bundled replays (`examples/replays/`)

Loadable one-click from the cockpit's **Replay** gallery (auto-discovered):

| File | What it is |
|---|---|
| `sample.events.jsonl` | Hand-authored reference tiny-CNN trajectory — the closed-loop hero. Loads offline. |
| `autonomous_research.events.jsonl` | **Real** autonomous Opus run: an LR range test that finds the optimum and self-corrects. |
| `live_steering_dod5.events.jsonl` | **Real** live Mode-A capture with human steering — NaN → learned bound → reshape (failures were steered). |
| `agent_edit_real.events.jsonl` | **Real** `agent-edit` capture editing real code (numpy MLP) — mechanism proof, scripted decisions. |
| `nanogpt.events.jsonl` | **Synthetic** stand-in for the serious modded-nanogpt run; replaced by a recorded run via `scripts/convert_nanogpt.py` (see [`asset-b/`](asset-b/)). |

## Repository layout

```text
backend/    FastAPI app — api/ (routes), events/ (JSONL log + models), state/ (builder),
            loop/ (planner, patcher, runner, evaluator, decider, constraints, steering, memory_writer, llm_client)
web/        Vite + React cockpit (src/components, src/lib, src/state)
kun/        the open contract — log.py (the ~5-line kun_log emit helper)
examples/   tiny_cnn/ trainer · replays/ (bundled trajectories) · external_loop_demo.py + external_loop_mode_b.py (wedge)
scripts/    gen_sample_events.py · convert_nanogpt.py (nanogpt run -> events)
asset-b/    Modal wrapper + runbook for the recorded nanogpt run (the serious "real code" demo asset)
runs/       per-mission event logs (gitignored)
docs/       00-spec (canonical) + design notes 01–12
```

## Documentation map

- [`docs/00-spec.md`](docs/00-spec.md) — **canonical build spec; read first (wins over 01–07 on conflict).**
- [`CONTRACT.md`](CONTRACT.md) — frozen cross-component interface (event schema, endpoints, ownership).
- [`DEMO_TEST_PLAN.md`](DEMO_TEST_PLAN.md) — the 1-min video recording set + full manual test/demo-rehearsal plan.
- [`docs/01-product-design.md`](docs/01-product-design.md) · [`02-technical-architecture.md`](docs/02-technical-architecture.md) · [`03-event-schema.md`](docs/03-event-schema.md) — product, architecture, the JSONL event contract.
- [`docs/04-implementation-plan.md`](docs/04-implementation-plan.md) · [`05-demo-plan.md`](docs/05-demo-plan.md) · [`06-agent-workstreams.md`](docs/06-agent-workstreams.md) — build order, demo, parallel workstreams.
- [`docs/07-modded-nanogpt-runbook.md`](docs/07-modded-nanogpt-runbook.md) — the serious recorded run (see also `asset-b/`).
- [`docs/08-agent-edit-design.md`](docs/08-agent-edit-design.md) · [`11-research-memory-design.md`](docs/11-research-memory-design.md) — `agent-edit` and two-tier memory design notes.
- [`docs/09-operator-checklist.md`](docs/09-operator-checklist.md) · [`10-implementation-handoff.md`](docs/10-implementation-handoff.md) · [`12-p1-handoff.md`](docs/12-p1-handoff.md) — ops + implementation handoff briefs.
