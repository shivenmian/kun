# Kun Agent Workstreams

## Purpose

Because the team is one person using multiple coding agents, split the work into isolated tracks with clear contracts.

The most important shared contract is the event schema in `docs/03-event-schema.md`.

## Workstream A: Backend and event log

### Goal

Build the FastAPI backend, JSONL flight recorder, and mission state reducer.

### Responsibilities

- FastAPI app setup.
- Pydantic event models.
- JSONL append/read.
- Mission directory structure under `runs/`.
- Event id/timestamp assignment.
- Mission state builder from events.
- HTTP endpoints for missions/events/state.
- SSE stream endpoint.

### Inputs

- Event schema doc.
- Mission spec shape.

### Outputs

- `backend/app/main.py`
- `backend/app/core/event_log.py`
- `backend/app/core/state_builder.py`
- `backend/app/api/missions.py`
- `backend/app/api/stream.py`
- tests or smoke scripts

### Acceptance criteria

- Can append and read events.
- Can stream events over SSE.
- Can rebuild mission state from a sample event log.

## Workstream B: Tiny CNN live loop

### Goal

Build the reliable live demo path.

### Responsibilities

- Fashion-MNIST CNN training script.
- Config file support.
- Metrics JSONL output.
- Experiment workspace creation.
- Config patching.
- Runner subprocess.
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
- runner script

### Acceptance criteria

- Runs on CPU.
- Writes metrics.
- Kun can execute 3-5 experiments.
- Produces events for proposal, diff, metrics, result, evaluation.

## Workstream C: Autoresearch planner/evaluator

### Goal

Implement proposal/evaluation/decision logic.

### Responsibilities

- Heuristic planner fallback.
- LiteLLM planner.
- Structured output validation.
- Evaluator verdicts.
- Decider next actions.
- Constraint handling.

### Inputs

- Current mission state.
- Previous experiments and metrics.
- Human constraints.

### Outputs

- `backend/app/loop/planner.py`
- `backend/app/loop/evaluator.py`
- `backend/app/loop/decider.py`
- `backend/app/loop/schemas.py`

### Acceptance criteria

- Loop works with no LLM via heuristic planner.
- Loop works with LiteLLM when key is configured.
- Invalid LLM JSON falls back safely.

## Workstream D: Frontend cockpit

### Goal

Build the main product UI.

### Responsibilities

- Vite React app.
- Event reducer.
- React Flow trajectory graph.
- Experiment detail panel.
- Metrics chart.
- Diff viewer.
- Event stream.
- Mission launcher.
- Fork dialog.

### Inputs

- Sample event logs.
- Backend API.

### Outputs

- `web/src/components/TrajectoryGraph.tsx`
- `web/src/components/ExperimentDetails.tsx`
- `web/src/components/MetricsChart.tsx`
- `web/src/components/DiffViewer.tsx`
- `web/src/components/EventStream.tsx`
- `web/src/components/ForkDialog.tsx`
- `web/src/state/eventReducer.ts`

### Acceptance criteria

- Can render static replay.
- Can subscribe to live SSE.
- Selecting a node updates detail panel.
- Fork UI can call backend.

## Workstream E: modded-nanogpt replay/import

### Goal

Create the serious credibility demo.

### Responsibilities

- Run or inspect modded-nanogpt session.
- Capture metrics/logs/diffs.
- Convert to Kun events.
- Create rich replay file.
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

### Start these immediately

1. Backend/event log.
2. Tiny CNN training script.
3. Frontend static replay UI.

### Start after first events exist

4. Live SSE.
5. Multi-experiment loop.
6. LiteLLM planner.

### Start tonight/in parallel

7. modded-nanogpt run/import.

### Start after core loop works

8. Fork.
9. Polish.
10. Desktop wrapper if time.

## Agent prompt templates

### Backend agent prompt

```text
You are implementing Kun's FastAPI backend and JSONL event log. Follow docs/03-event-schema.md exactly. Build minimal endpoints for creating missions, appending/reading events, reconstructing mission state, and streaming events via SSE. Keep code simple and demo-ready. Do not implement UI. Do not change event semantics without updating docs.
```

### Tiny CNN agent prompt

```text
You are implementing Kun's live ML demo adapter. Build a Fashion-MNIST tiny CNN training script that reads YAML config, trains quickly on CPU/GPU, and writes metrics.jsonl. Then implement a backend adapter that creates per-experiment configs, runs the command, parses metrics, and emits Kun events. Prefer reliability over model sophistication.
```

### Frontend agent prompt

```text
You are implementing Kun's cockpit UI. Build a Vite React app with React Flow trajectory graph, experiment details panel, metrics chart, diff viewer, event stream, and fork dialog. The UI is driven by Kun JSONL events and should work with both static replay files and live SSE events. Keep the UI trajectory-first.
```

### modded-nanogpt agent prompt

```text
You are building Kun's modded-nanogpt replay/import path. Take logs, metrics, diffs, and experiment notes from a modded-nanogpt-style run and convert them into Kun events. The replay should tell a compelling research story: baseline, improvements, failures, learned constraints, throughput tradeoffs, and a forkable best branch.
```
