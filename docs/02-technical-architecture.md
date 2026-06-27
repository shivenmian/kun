# Kun Technical Architecture

## Architecture summary

Kun should be built as a local web MVP first. A desktop shell can be added later.

```text
Frontend Cockpit
  Vite React + React Flow + charts + diff viewer
      |
      | HTTP + SSE
      v
Backend API
  FastAPI mission controller + event stream
      |
      v
Autoresearch Loop
  Planner -> Patcher -> Runner -> Parser -> Evaluator -> Decider
      |
      v
Project Adapter
  train command, editable files, metric parser, constraints
      |
      v
Experiment Workspace
  copied repo/template per experiment, logs, metrics, diffs
      |
      v
Event Log / Flight Recorder
  JSONL events + SQLite materialized state
```

## Recommended stack

```text
Frontend: Vite React
Language: TypeScript
UI: Tailwind + shadcn/ui
Graph: React Flow
Charts: Recharts
Diff: Monaco diff viewer or react-diff-viewer
Backend: FastAPI
Language: Python
Event stream: Server-Sent Events first, WebSocket only if needed
Storage: JSONL event log + SQLite
Agent abstraction: LiteLLM Python SDK
Live ML task: Fashion-MNIST tiny CNN
Serious replay: modded-nanogpt recorded trajectory
```

## Repository structure

Suggested initial structure:

```text
kun/
  README.md
  docs/
    01-product-design.md
    02-technical-architecture.md
    03-event-schema.md
    04-implementation-plan.md
    05-demo-plan.md
    06-agent-workstreams.md
    07-modded-nanogpt-runbook.md

  backend/
    app/
      main.py
      api/
        missions.py
        events.py
        stream.py
      core/
        event_log.py
        mission_controller.py
        state_builder.py
        settings.py
      loop/
        planner.py
        patcher.py
        runner.py
        metrics.py
        evaluator.py
        decider.py
      adapters/
        base.py
        tiny_cnn.py
        modded_nanogpt.py
      models/
        events.py
        mission.py
        experiment.py
    pyproject.toml

  web/
    src/
      main.tsx
      App.tsx
      api/
        client.ts
        sse.ts
      components/
        MissionLauncher.tsx
        TrajectoryGraph.tsx
        ExperimentDetails.tsx
        MetricsChart.tsx
        DiffViewer.tsx
        EventStream.tsx
        ForkDialog.tsx
        TopBar.tsx
        Sidebar.tsx
      state/
        missionStore.ts
        eventReducer.ts
      types/
        events.ts
        mission.ts
    package.json

  examples/
    tiny_cnn/
      train.py
      config.yaml
      mission.yaml
      README.md
    replays/
      modded_nanogpt_demo.events.jsonl
```

If solo speed matters, it is acceptable to flatten this. The key is keeping the event schema clean.

## Core backend components

### Mission Controller

Owns mission lifecycle:

- create mission
- start mission
- stop/pause mission
- fork from experiment
- load replay
- keep current mission state
- enforce budget and stop conditions

### Event Log / Flight Recorder

Source of truth for the system.

Responsibilities:

- append JSONL events
- assign event ids and timestamps
- stream events to UI
- reload events from disk
- rebuild materialized mission state
- support replay mode

The UI should be reconstructable from the event log. This makes live mode and replay mode use the same path.

### State Builder

Converts the append-only event stream into materialized state:

- missions
- experiments
- branches
- metrics
- diffs
- constraints
- current best experiment
- live/running statuses

This can exist in backend and frontend. For MVP, duplicate minimal logic if needed, but prefer shared event semantics.

### Autoresearch Loop

The loop can be implemented as one orchestrator with internal steps:

```text
while budget remains:
  current_state = summarize mission state
  proposal = planner.propose(current_state)
  patch = patcher.apply(proposal)
  result = runner.run(patch)
  metrics = parser.parse(result)
  evaluation = evaluator.evaluate(metrics, state)
  decision = decider.decide(evaluation, state)
  emit events throughout
```

For MVP, the planner/evaluator/decider can be simple and deterministic first. Add LiteLLM once the evented loop works.

## Project Adapter interface

The adapter lets Kun be generic without claiming perfect arbitrary repo support.

A project adapter defines:

```yaml
project_name: string
root: path
train_command: string
metric_source: stdout | metrics_jsonl | metrics_file
primary_metric:
  name: string
  direction: maximize | minimize
editable_files:
  - path
constraints:
  max_runtime_sec: number
  fail_on_nan: boolean
artifacts:
  - path_globs
```

Python shape:

```python
class ProjectAdapter:
    name: str

    def prepare_experiment(self, mission, proposal) -> ExperimentWorkspace:
        ...

    def apply_changes(self, workspace, proposal) -> DiffResult:
        ...

    def command_for(self, workspace) -> list[str]:
        ...

    def parse_metrics(self, workspace, stdout_path, stderr_path) -> list[MetricEvent]:
        ...

    def collect_artifacts(self, workspace) -> list[ArtifactRef]:
        ...
```

## Tiny CNN adapter

MVP adapter for live demo.

Characteristics:

- uses Fashion-MNIST
- patches config only
- writes metrics.jsonl
- runs quickly on CPU or GPU
- supports 30-90 second experiments

Editable knobs:

```text
learning_rate
optimizer
batch_size
dropout
conv_channels
weight_decay
augmentation
scheduler
```

Implementation shortcut:

- The training script reads `config.yaml`.
- The patcher writes a new config per experiment.
- The runner invokes `python train.py --config runs/exp_004/config.yaml`.
- The script writes `metrics.jsonl` with train/val metrics.

## modded-nanogpt adapter

MVP role: serious replay and optional real run ingestion.

Do not depend on live modded-nanogpt execution during judging.

Adapter goals:

- parse logs/metrics into Kun events
- capture code/config diffs
- capture final score, target-loss crossing, throughput, failures
- convert tonight's run into `events.jsonl`

If there is time, implement a real adapter that can run a short mode. If not, implement a converter/importer.

## LLM provider abstraction

Use LiteLLM Python SDK to avoid provider lock-in.

UI settings:

- provider
- model
- API key
- temperature
- max tokens
- test connection

Backend env support:

```text
OPENAI_API_KEY
ANTHROPIC_API_KEY
GEMINI_API_KEY
```

For MVP, storing API keys in `.env` or local SQLite is acceptable. Do not overbuild desktop keychain support.

### Planner output schema

The planner should return strict JSON:

```json
{
  "hypothesis": "Lower learning rate with AdamW may improve validation stability.",
  "changes": {
    "learning_rate": 0.001,
    "optimizer": "adamw",
    "dropout": 0.25,
    "batch_size": 128
  },
  "expected_outcome": "Validation accuracy should improve without slower convergence.",
  "risk": "Too much dropout may underfit.",
  "rationale": "Previous experiments showed overfitting and unstable validation accuracy."
}
```

Validate this output before applying changes.

## Fork implementation

Fork should be generic and evented.

```text
POST /missions/{mission_id}/fork
  experiment_id: exp_009
  instruction: keep cosine scheduler, ban lr > 0.003
```

Flow:

```text
1. Load selected experiment state.
2. Create a new branch.
3. Emit branch_created/fork_created.
4. Add human constraint to mission state.
5. Ask planner for next proposal with branch context.
6. Emit experiment_proposed.
7. Optionally run immediately.
```

For modded-nanogpt replay, fork can create/queue a new branch without actually launching a huge run. For tiny CNN, fork should execute live if possible.

## API endpoints

Initial API surface:

```text
GET  /health
GET  /settings
POST /settings/llm/test

GET  /missions
POST /missions
GET  /missions/{mission_id}
POST /missions/{mission_id}/start
POST /missions/{mission_id}/stop
POST /missions/{mission_id}/fork
GET  /missions/{mission_id}/events
GET  /missions/{mission_id}/stream
GET  /missions/{mission_id}/experiments
GET  /missions/{mission_id}/state

POST /replays/load
GET  /replays
```

Use SSE for live stream:

```text
GET /missions/{mission_id}/stream
Content-Type: text/event-stream
```

## Frontend state model

The frontend should consume events and reduce them into UI state.

Main state:

```ts
type MissionState = {
  mission: Mission;
  experiments: Record<string, Experiment>;
  branches: Record<string, Branch>;
  metricsByExperiment: Record<string, MetricPoint[]>;
  events: KunEvent[];
  selectedExperimentId?: string;
  currentBestExperimentId?: string;
};
```

Views:

- MissionLauncher
- Sidebar
- TopBar
- TrajectoryGraph
- ExperimentDetails
- MetricsChart
- DiffViewer
- EventStream
- ForkDialog

## Reliability principles

- Make the tiny CNN live path work even without GPU.
- Make replay mode work even if live loop breaks.
- Make the modded-nanogpt replay impressive even if the real run is partial.
- Keep event log source-of-truth clean.
- Use deterministic fallback planner before LiteLLM.
- Never block core UI on desktop packaging.

## Packaging

Do not start with desktop packaging.

Build the local web app first:

```text
backend: http://localhost:8000
frontend: http://localhost:5173
```

If time remains, wrap with Electron or Tauri. The desktop shell is polish, not the MVP.
