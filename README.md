# Kun

Kun is a mission-control cockpit for autonomous ML experiment loops.

It is not a W&B replacement and it is not a generic agent chat UI. Kun is designed around a different primitive: the **research trajectory**. A trajectory captures why an autonomous researcher ran each experiment, what changed, what happened, what evidence came back, what the agent learned, and where a human can steer next.

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

## Hackathon scope

Kun should support:

1. Creating a research mission.
2. Running a real autonomous experiment loop on a tiny ML task.
3. Recording every important action as structured JSONL events.
4. Rendering the trajectory as a live cockpit UI.
5. Replaying a saved richer session, especially a modded-nanogpt-style optimization run.
6. Forking from a prior experiment with a human constraint.

## Recommended MVP stack

```text
Frontend: Vite React
UI: Tailwind + shadcn/ui
Graph: React Flow
Charts: Recharts
Diff viewer: Monaco diff viewer or react-diff-viewer
Backend: FastAPI
Event stream: Server-Sent Events first, WebSocket only if needed
Storage: JSONL event log + SQLite
Agent provider abstraction: LiteLLM Python SDK
Live task: Fashion-MNIST tiny CNN
Serious replay: modded-nanogpt recorded trajectory
```

## Documentation map

- [`docs/01-product-design.md`](docs/01-product-design.md) - product thesis, scope, UX, features, non-goals.
- [`docs/02-technical-architecture.md`](docs/02-technical-architecture.md) - system architecture and implementation shape.
- [`docs/03-event-schema.md`](docs/03-event-schema.md) - JSONL event contract and examples.
- [`docs/04-implementation-plan.md`](docs/04-implementation-plan.md) - build order, milestones, and acceptance criteria.
- [`docs/05-demo-plan.md`](docs/05-demo-plan.md) - final demo strategy and script.
- [`docs/06-agent-workstreams.md`](docs/06-agent-workstreams.md) - parallel coding-agent tasks.
- [`docs/07-modded-nanogpt-runbook.md`](docs/07-modded-nanogpt-runbook.md) - plan for the serious recorded run.
