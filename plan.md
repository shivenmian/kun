You are implementing Kun, a hackathon MVP from scratch in /Users/shivenmian/code/personal/kun.

Kun is a mission-control cockpit for autonomous ML experiment loops. The product thesis:

W&B is run-centric. Agent observability is trace-centric. Kun is trajectory-centric: it shows why an autonomous researcher ran each experiment, what changed, what evidence came back, what the agent learned, and where the human can steer next.

Important: do not let implementation drift into infrastructure or polish before the static replay cockpit works. Static replay is the first milestone and the first demo artifact.

Read these docs first and treat them as source of truth:

* README.md
* docs/01-product-design.md
* docs/02-technical-architecture.md
* docs/03-event-schema.md
* docs/04-implementation-plan.md
* docs/05-demo-plan.md
* docs/06-agent-workstreams.md
* docs/07-modded-nanogpt-runbook.md

Goal

Build a working MVP with:

1. A local web cockpit UI.
2. A FastAPI backend.
3. A JSONL event-log / flight-recorder system.
4. A replay mode that can render a saved events.jsonl.
5. A live Fashion-MNIST tiny CNN autonomous experiment loop.
6. A trajectory graph where experiment nodes are connected by decisions.
7. An experiment detail panel with hypothesis, params, metrics, diff, verdict, and rationale.
8. A metrics chart.
9. A code/config diff viewer.
10. A live event stream.
11. Fork-from-node with a human constraint.
12. LiteLLM provider-agnostic planner, after the heuristic loop works.
13. A modded-nanogpt replay/import path if time allows.

Do not build a full W&B replacement. Do not build generic arbitrary repo support. Do not build distributed GPU orchestration. Do not build a complex multi-agent framework. Keep the product trajectory-first.

NON-NEGOTIABLE IMPLEMENTATION PRIORITIES

Follow these rules unless the user explicitly overrides them.

1. Build static replay first

Highest-priority implementation rule: build static replay first.

Before implementing FastAPI, live training, LiteLLM, desktop wrapping, GPU setup, or modded-nanogpt execution, create:

sample_data/replays/sample-events.jsonl

Then make the web UI render it into:

events.jsonl
→ React Flow trajectory graph
→ clickable experiment details
→ metrics chart
→ code/config diff panel
→ event stream

This is the first success criterion. Do not proceed to live execution until the static replay path proves the core product visual.

2. Do not start with desktop wrapping, GPU setup, or modded-nanogpt

Do not begin with:

* Electron/Tauri wrapping
* GPU setup
* DigitalOcean/Modal/Prime Intellect setup
* live modded-nanogpt execution
* complex arbitrary repo support
* W&B integration

These are later-stage polish or credibility tasks. The core product is the trajectory cockpit.

3. First success criterion

The first working milestone is:

sample_data/replays/sample-events.jsonl
→ React Flow trajectory graph
→ clickable experiment details
→ metrics chart
→ diff panel

A user should be able to open Kun, load a saved replay, click an experiment node, and understand:

* why this experiment happened
* what changed
* what metrics came back
* what verdict/rationale the agent produced
* what branch/decision followed

4. Second success criterion

The second working milestone is:

Fashion-MNIST loop emits the same event schema
→ backend streams those events
→ UI updates live

The live loop should run at least 3 autonomous experiments and produce the same kind of trajectory as the static replay.

5. Event log is the single source of truth

Keep one source of truth: the JSONL event log.

No separate hidden state model should be required to reconstruct the mission UI. Derived UI state is allowed, but it must be reconstructable from events.

Replay mode and live mode should consume the same event shape.

If adding SQLite, use it only as a convenience/index/cache layer. The JSONL flight recorder remains canonical.

6. Integration discipline

Use worktrees and branches for subagents. No subagent should work directly on main.

Rules:

* Each subagent owns a worktree and branch.
* Each subagent lists files it plans to modify before modifying them.
* Do not edit files owned by another subagent without coordination.
* Avoid broad refactors while other branches are active.
* Do not run repo-wide auto-formatters from a feature branch.
* Commit frequently with clear messages.
* Merge one branch at a time.

7. Keep every task tied to the demo

The main risk is overbuilding.

Every implementation task should support one of the three demo paths:

1. Serious modded-nanogpt replay.
2. Reliable live Fashion-MNIST loop.
3. Fork/steering action.

If a task does not directly improve one of those demo paths, defer it.

PREFERRED STACK
Use this stack unless there is a very strong reason not to:

* Frontend: Vite + React + TypeScript
* UI: Tailwind + shadcn/ui or lightweight custom components
* Graph: React Flow
* Charts: Recharts
* Diff viewer: Monaco diff viewer or react-diff-viewer
* Backend: Python FastAPI
* Event streaming: Server-Sent Events first, WebSocket only if necessary
* Storage: JSONL event logs as source of truth; SQLite only for convenience/indexing if needed
* Agent provider: LiteLLM Python SDK
* ML live demo: Fashion-MNIST tiny CNN

Repository expectations

Set up a simple monorepo-ish structure:

/Users/shivenmian/code/personal/kun
  apps/
    web/
    api/
  examples/
    fashion_mnist/
  sample_data/
    replays/
  docs/
  scripts/

Prefer boring, easy-to-debug code over clever abstractions.

Critical architecture rule

The event log is the product backbone.

Everything meaningful must emit JSONL events. The UI should be able to reconstruct mission state from the event log. Replay mode should consume the same events as live mode.

Core event shape:

{
  "event_id": "evt_...",
  "timestamp": "2026-...",
  "mission_id": "mission_...",
  "experiment_id": "exp_...",
  "parent_experiment_id": "exp_...",
  "type": "metric_logged",
  "payload": {}
}

Core event types:

mission_created
experiment_proposed
experiment_started
file_diff_created
command_started
metric_logged
experiment_finished
experiment_failed
evaluation_created
decision_created
constraint_learned
branch_created
fork_created
replay_loaded

Implement this early and keep it stable.

Implementation strategy

Build in this order:

Milestone 0: Repo scaffold

Create:

* frontend app
* backend app
* shared/sample event schema docs or TS/Python types
* sample events.jsonl
* basic dev commands

Expected outcome:

cd /Users/shivenmian/code/personal/kun
# one command or two commands should run frontend/backend locally

One command or two commands should run frontend/backend locally.

MILESTONE 1: Static replay UI

Before building live execution, make the UI render a sample replay.

Implement:

* load sample events.jsonl
* reconstruct experiments
* render experiment trajectory graph
* click node to open detail panel
* show event stream
* show basic metrics chart
* show fake/sample diff viewer

This derisks the product fastest.

Milestone 2: Backend event log + SSE

Implement FastAPI backend:

POST /missions
POST /missions/{mission_id}/start
POST /missions/{mission_id}/fork
GET  /missions/{mission_id}/events
GET  /missions/{mission_id}/stream
GET  /missions/{mission_id}/experiments

Use JSONL files under a local data directory, e.g.:

.kun/
  missions/
    mission_<id>/
      events.jsonl
      artifacts/
      experiments/

SSE stream should emit events as they are appended.

Milestone 3: Fashion-MNIST tiny CNN runner

Build a small training example under:

examples/fashion_mnist/

It should have:

* train.py
* config.yaml
* writes metrics.jsonl
* supports quick runs, ideally 30–90 seconds
* works CPU-only if needed
* optionally uses GPU if available

Agent-controlled parameters:

learning_rate
optimizer
dropout
batch_size
conv_channels
weight_decay
augmentation_enabled
scheduler

For MVP, patch config only. Do not allow arbitrary code edits in the live CNN loop until the config-based loop is stable.

Milestone 4: Heuristic autonomous loop

Before using LiteLLM, implement a deterministic/heuristic planner so the entire loop works reliably.

Loop:

create mission
→ propose experiment
→ write config copy
→ emit proposed event
→ run train command
→ parse metrics
→ evaluate result
→ emit decision/verdict
→ repeat until budget exhausted

This should generate a real trajectory with at least 3–5 experiments.

Milestone 5: UI live mode

Connect frontend to backend SSE.

When a live mission runs:

* event stream updates live
* graph updates live
* running node status updates
* metrics chart updates
* node detail panel works

Milestone 6: Fork from node

Implement the core intervention:

Fork from exp_N with human constraint.

The fork should:

* create a new branch
* preserve parent experiment link
* record human instruction/constraint
* propose a next experiment from that node
* optionally run it immediately

Example:

Fork from exp_004.
Constraint: keep AdamW, but ban dropout > 0.4 because it underfit.

Milestone 7: LiteLLM planner

After the heuristic loop works, add LiteLLM.

Use structured JSON output only. The planner should produce:

{
  "hypothesis": "Lower LR with AdamW may improve validation stability.",
  "changes": {
    "learning_rate": 0.001,
    "optimizer": "adamw",
    "dropout": 0.25
  },
  "expected_outcome": "Validation accuracy improves without slower convergence.",
  "risk": "May underfit if dropout is too high."
}

Add simple UI/settings for:

* provider
* model
* API key or env var name
* test connection

Use environment variables first if easier. Do not spend too much time on secure key storage.

Milestone 8: modded-nanogpt replay/import

Do not make live modded-nanogpt execution required for the demo.

Implement either:

* an importer/converter from logs/diffs/metrics to Kun events, or
* a rich hand-authored/reconstructed events.jsonl replay based on a real run.

The demo needs a serious replay that shows:

* baseline
* improvements
* failures
* NaNs/instability
* throughput tradeoff
* learned constraints
* forkable branch
* best run

UI requirements

The UI should prioritize one memorable screen.

Layout:

Left: missions / branches / saved replays
Top: mission name, best metric, current run, budget used, mode live/replay
Center: research trajectory graph
Right: selected experiment detail
Bottom or side: live event stream

Experiment node should show:

* experiment id
* short hypothesis
* metric delta
* status

Statuses:

baseline
proposed
running
success
failed
promoted
rejected
forked

Experiment detail panel should show:

* hypothesis
* parent experiment
* changed params
* code/config diff
* command
* metrics
* verdict
* rationale
* evidence
* fork button

Add a small “learned constraints” panel if easy:

- LR > 0.003 caused instability twice.
- Dropout > 0.4 underfit.
- AdamW improved validation accuracy in 2/3 branches.

Parallel work / subagent coordination

Use Claude Code subagents or parallel sessions, but avoid collisions. Use git worktrees and separate branches.

Main repo path:

/Users/shivenmian/code/personal/kun

Before starting parallel work, create worktrees from main:

cd /Users/shivenmian/code/personal/kun
git status
git checkout main
git pull --ff-only || true
mkdir -p /Users/shivenmian/code/personal/kun-worktrees
git worktree add /Users/shivenmian/code/personal/kun-worktrees/kun-api -b feature/api-event-log
git worktree add /Users/shivenmian/code/personal/kun-worktrees/kun-web -b feature/web-cockpit
git worktree add /Users/shivenmian/code/personal/kun-worktrees/kun-fashion -b feature/fashion-mnist-loop
git worktree add /Users/shivenmian/code/personal/kun-worktrees/kun-replay -b feature/replay-samples
git worktree add /Users/shivenmian/code/personal/kun-worktrees/kun-polish -b feature/demo-polish

Assign subagents like this:

Subagent A: API / event log

Worktree:

/Users/shivenmian/code/personal/kun-worktrees/kun-api

Branch:

feature/api-event-log

Owns:

apps/api/**
backend event log implementation
SSE stream
mission endpoints
event schema Python models
local .kun mission storage

Must avoid editing:

apps/web/**
examples/fashion_mnist/**
sample_data/**

Deliverable:

* FastAPI server runs.
* Can append/read/stream events.
* Can create/start/fork mission with stub events.
* Includes simple tests or scripts.

Subagent B: Web cockpit UI

Worktree:

/Users/shivenmian/code/personal/kun-worktrees/kun-web

Branch:

feature/web-cockpit

Owns:

apps/web/**
frontend components
trajectory graph
detail panel
metrics chart
diff viewer
event stream UI

Must avoid editing:

apps/api/**
examples/fashion_mnist/**

Deliverable:

* Vite React app runs.
* Can load a local/static sample events.jsonl.
* Renders trajectory graph and experiment details.
* Later can connect to API stream.

Subagent C: Fashion-MNIST loop

Worktree:

/Users/shivenmian/code/personal/kun-worktrees/kun-fashion

Branch:

feature/fashion-mnist-loop

Owns:

examples/fashion_mnist/**
apps/api/research_loop/** only if agreed
scripts/run_fashion_mission.py

Must avoid editing frontend except maybe docs.

Deliverable:

* train.py runs with config.
* Emits metrics.jsonl.
* Heuristic autonomous loop runs 3–5 experiments.
* Emits Kun-compatible events.

Subagent D: Replay samples / event fixtures

Worktree:

/Users/shivenmian/code/personal/kun-worktrees/kun-replay

Branch:

feature/replay-samples

Owns:

sample_data/replays/**
scripts/convert_replay.py
docs updates related to sample events

Deliverable:

* Rich sample events.jsonl.
* At least one tiny CNN replay.
* At least one modded-nanogpt-style replay.
* Events conform to schema.

Subagent E: Demo polish

Worktree:

/Users/shivenmian/code/personal/kun-worktrees/kun-polish

Branch:

feature/demo-polish

Owns:

docs demo updates
README usage
scripts/dev.sh
scripts/demo.sh
small styling only after web branch merges

Must avoid touching core API/UI until integration.

Deliverable:

* README.md quickstart.
* scripts/dev.sh
* scripts/demo.sh
* demo script notes.
* sample screenshots if possible.

Collision rules

1. No subagent should work directly on main.
2. Every subagent uses its assigned worktree and branch.
3. Each subagent must list files it plans to modify before modifying them.
4. If a task requires editing files owned by another subagent, stop and ask for coordination.
5. Prefer additive changes over refactors until integration.
6. Keep interfaces stable:
    * event schema
    * API endpoint names
    * sample event file paths
7. Do not run broad auto-formatters over the entire repo from a feature branch.
8. Commit frequently with clear messages.
9. Before merging a branch, run tests/dev commands for that area.
10. Integration should happen in main repo, one branch at a time.

Suggested integration order

Merge in this order:

1. feature/replay-samples
2. feature/web-cockpit
3. feature/api-event-log
4. feature/fashion-mnist-loop
5. feature/demo-polish

Reason:

* UI can first work against static replay.
* API can then replace static data with live events.
* Fashion loop can then emit real events.
* Polish happens last.

If dependencies require, adjust, but do not merge multiple large branches blindly.

Quality bar

The MVP is successful when:

1. events.jsonl replay renders a convincing trajectory graph.
2. Clicking an experiment shows hypothesis, diff, metrics, verdict, rationale.
3. Backend can stream events live.
4. Fashion-MNIST loop can run at least 3 autonomous experiments.
5. UI updates as events arrive.
6. Fork-from-node creates a new branch and records human constraint.
7. Demo can show:
    * serious modded-nanogpt replay
    * live tiny CNN run
    * fork/steering action

Important product constraints

Keep the story clean:

* Do not call this a W&B replacement.
* Do not overbuild generic dashboards.
* Do not make arbitrary repo support a blocker.
* Do not make live modded-nanogpt execution a blocker.
* The core product object is the research trajectory.

First task

Start by inspecting the repo and docs:

cd /Users/shivenmian/code/personal/kun
ls
find docs -maxdepth 2 -type f -print
sed -n '1,220p' docs/04-implementation-plan.md
sed -n '1,220p' docs/03-event-schema.md

Then create the worktrees and begin with Milestone 0 and Milestone 1.

Do not start by beautifying the UI. Start by making sample_data/replays/sample-events.jsonl render into a trajectory graph.
