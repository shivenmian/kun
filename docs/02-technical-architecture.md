# Kun Technical Architecture

> **Reconciled with [`00-spec.md`](00-spec.md) (canonical; wins on any conflict).** v4 deltas: **two first-class modes** — Mode A (Kun drives the loop) and Mode B (Kun observes/steers an external loop), converging on the same event log, with a Mode-B feedback channel (`GET /missions/{id}/state` exposes active constraints + pending fork/instruct for the external loop to read back); **LiteLLM is back IN** for provider-agnostic planning + a minimal per-mission model picker (powers model benchmarking) — only the *elaborate* settings UI (temperature / max-tokens / `test connection`) stays out; the **code patcher** is one interface with two implementations — `config-patch` (P0) and `agent-edit` (P1, orchestrates Claude Code/Codex as a subprocess to edit real model code and return the diff), mapped onto `ProjectAdapter.apply_changes`; **live fork execution** (Mode A), the **approval gate**, **mid-run instruct**, and **commit-per-node** are core (P1); new events `instruction_added` / `experiment_approved` / `experiment_rejected` (doc 03); new endpoints `POST /missions/{id}/ingest`, `POST /missions/{id}/approve`, `POST /missions/{id}/instruct`, and the feedback-channel use of `GET /missions/{id}/state`; `POST /settings/llm/test` is dropped. Retained: SQLite cut (JSONL + in-memory only), the LLM is the driver (heuristic planner is fallback/baseline only), engine-agnostic producers + the ~5-line `kun_log(...)` emit helper as a shipped first-class deliverable (the wedge), `operator` + `valid`/`buggy` + `schema_version` on the materialized model, ResearchMemoryPanel + CompareView (core), react-diff-viewer (not Monaco). Everything is tagged **P0/P1/P2**. The ProjectAdapter interface and fork flow below are still valid; the API surface is updated below.

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
  JSONL events + in-memory materialized state (no SQLite for MVP)
```

## Recommended stack

```text
Frontend: Vite React
Language: TypeScript
UI: Tailwind + shadcn/ui
Graph: React Flow
Charts: Recharts
Diff: react-diff-viewer (not Monaco)
Backend: FastAPI
Language: Python
Event stream: Server-Sent Events first, WebSocket only if needed
Storage: JSONL event log only (in-memory state builder; no SQLite for MVP)
Agent abstraction: LiteLLM for provider-agnostic planning + a minimal per-mission model picker (powers benchmarking; no elaborate settings UI)
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
        CompareView.tsx
        CrossModelCompareView.tsx
        ResearchMemoryPanel.tsx
        Leaderboard.tsx
        EventStream.tsx
        ForkDialog.tsx
        ApprovalGate.tsx
        InstructBox.tsx
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

For MVP, the **LLM is the driver**: it proposes the hypothesis *and* the actual config/code change, and evaluates results. A deterministic heuristic planner exists only as a **fallback** (on schema-validation failure) and an **offline/no-key baseline** — it is not the primary path. Wire the evented loop and the LLM driver together; do not ship a deterministic-only loop.

**Two first-class modes (spec §4).** This Planner→Patcher→Runner→Parser→Evaluator→Decider loop is **Mode A — Kun drives**: Kun owns execution, so steering has teeth (fork executes, constraints bind, the approval gate blocks the next run). In **Mode B — Kun observes/steers an external loop** (Claude Code / Codex / a script emitting via `kun_log`), Kun is the cockpit + memory and does not run this loop. Both modes converge on the same event log and render through the same UI; the mode is a property of who owns execution. Mode-B steering becomes real via the **feedback channel**: the external loop polls `GET /missions/{id}/state` (active constraints + pending fork/instruct) at the top of each iteration and obeys.

**The patcher = one interface, two implementations (maps onto `ProjectAdapter.apply_changes`).** `config-patch` (P0) writes changed keys into a config file — fast, reliable, the tiny-CNN path and always-available fallback. `agent-edit` (P1) hands the proposed change to a **coding agent (Claude Code / Codex) run as a subprocess** to edit *real model code* and returns the resulting diff (emitted as `file_diff_created`); this is what lets Kun autoresearch any model, not just config knobs. The runner then executes the train/eval command on the patched per-experiment workspace.

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

## LLM provider — LiteLLM is IN

**In MVP:** LiteLLM backs provider-agnostic planning behind a single `propose(...)` boundary, plus a **minimal per-mission model picker** (the mission spec's `model` field is a LiteLLM model id; the topbar shows it). This is what unlocks **model benchmarking** — the same mission run under N models, compared as autoresearchers (spec §7 P2, §8 Beat 5). Read keys from env vars.

```text
ANTHROPIC_API_KEY   # plus any other provider keys LiteLLM routes to
```

Storing keys in `.env` is fine. No SQLite, no desktop keychain.

**Out of scope (the elaborate settings UI only):** the full provider/model/API-key/temperature/max-tokens/`test connection` settings panel. The per-mission picker is a model dropdown, not a settings suite — keep it minimal. `POST /settings/llm/test` is dropped.

### Planner output schema

The planner should return strict JSON:

```json
{
  "operator": "improve",
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
7. In Mode A, execute the run immediately (or hold at the approval gate if enabled, emitting experiment_approved / experiment_rejected before running); in Mode B, expose it via GET /missions/{id}/state for the external loop to pick up.
```

**Live fork execution is core (P1).** In **Mode A**, fork **executes a real run** on the new branch (this is the steering-with-teeth beat). In **Mode B**, fork **queues an instruction** the external loop reads back via the feedback channel (`GET /missions/{id}/state`). For the heavy modded-nanogpt target, fork can create/queue a new branch without launching a full run; for tiny CNN (Mode A) it executes live.

## API endpoints

Initial API surface:

```text
GET  /health
GET  /settings

GET  /missions
POST /missions
GET  /missions/{mission_id}
POST /missions/{mission_id}/start
POST /missions/{mission_id}/stop
POST /missions/{mission_id}/fork
POST /missions/{mission_id}/approve     # approval gate: approve/reject/edit a pending proposal (P1)
POST /missions/{mission_id}/instruct    # mid-run NL instruct -> instruction_added (P1)
POST /missions/{mission_id}/ingest      # external producer path: POST a kun_log dict (server fills the envelope)
GET  /missions/{mission_id}/events
GET  /missions/{mission_id}/stream
GET  /missions/{mission_id}/experiments
GET  /missions/{mission_id}/state       # Mode-B feedback channel: active constraints + pending fork/instruct (P1)

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

- MissionLauncher (includes the minimal per-mission model picker — LiteLLM model id)
- Sidebar
- TopBar (status: mission name, best metric, current experiment, budget used, mode [A-live / B-observe / replay / paused], runtime, model)
- TrajectoryGraph (nodes badged by operator, colored by valid/buggy status)
- ExperimentDetails
- MetricsChart
- DiffViewer
- CompareView (P1 — diff two nodes' configs + overlay their metric curves; moved out of the P0 node-view, which is the detail/diff/leaderboard triad)
- ResearchMemoryPanel (core — mission-wide accumulated constraints/learnings)
- CrossModelCompareView (P2 — same mission under N models; ranks models as autoresearchers; spec §8 Beat 5)
- Leaderboard (results table sorted by metric)
- EventStream
- ForkDialog
- ApprovalGate (approve / reject / edit a pending proposal; P1)
- InstructBox (mid-run NL instruct -> instruction_added; P1)

## Reliability principles

- Make the tiny CNN live path work even without GPU.
- Make replay mode work even if live loop breaks.
- Make the modded-nanogpt replay impressive even if the real run is partial.
- Keep event log source-of-truth clean.
- Heuristic planner is a fallback/baseline only (used on LLM schema-validation failure or no-key mode); the LLM drives the happy path.
- Never block core UI on desktop packaging.

## Packaging

Do not start with desktop packaging.

Build the local web app first:

```text
backend: http://localhost:8000
frontend: http://localhost:5173
```

If time remains, wrap with Electron or Tauri. The desktop shell is polish, not the MVP.
