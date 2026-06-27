# Kun Implementation Plan

## Build philosophy

Build the working research loop and event log first. The UI should be a projection of the event log. Desktop packaging comes last, if at all.

The correct order is:

```text
Event schema
-> Tiny live loop
-> Basic backend stream
-> Cockpit UI
-> Replay
-> Fork
-> modded-nanogpt import/replay
-> polish/desktop
```

## Milestone 0: Repo scaffold

### Goal

Create the project skeleton with backend, frontend, examples, and docs.

### Tasks

- Add `backend/` FastAPI app.
- Add `web/` Vite React app.
- Add `examples/tiny_cnn/` training task.
- Add `examples/replays/` for saved event logs.
- Add docs.

### Acceptance criteria

- `backend` can start.
- `web` can start.
- README explains local dev commands.

## Milestone 1: Event log and state builder

### Goal

Create the source-of-truth event system.

### Tasks

- Define Pydantic models for core events.
- Implement JSONL append writer.
- Implement event id/timestamp assignment.
- Implement `GET /missions/{id}/events`.
- Implement state builder that derives experiments and metrics from events.
- Add simple sample events file.

### Acceptance criteria

- Can append events to `runs/<mission_id>/events.jsonl`.
- Can reload a mission from JSONL.
- Can derive a mission state object with experiments/metrics.

## Milestone 2: Tiny CNN training script

### Goal

Have a real ML task that runs quickly and emits metrics.

### Recommended task

Fashion-MNIST tiny CNN.

### Training script requirements

- Reads `config.yaml`.
- Trains for a small number of epochs or steps.
- Writes `metrics.jsonl`.
- Writes stdout/stderr logs.
- Supports timeout-friendly runs.
- Works on CPU, uses GPU if available.

### Config knobs

```yaml
learning_rate: 0.001
optimizer: adamw
batch_size: 128
dropout: 0.25
conv_channels: 32
weight_decay: 0.0001
augmentation: false
scheduler: none
epochs: 2
seed: 42
```

### Acceptance criteria

- `python examples/tiny_cnn/train.py --config examples/tiny_cnn/config.yaml` runs successfully.
- It writes `metrics.jsonl` with train/val metrics.
- Runtime is reasonable for live demo.

## Milestone 3: One-experiment runner

### Goal

Run one experiment through Kun's backend loop and emit events.

### Tasks

- Create mission from YAML.
- Create experiment workspace.
- Patch config from a proposed change.
- Emit `experiment_proposed`.
- Emit `file_diff_created`.
- Run command.
- Stream or collect metrics.
- Emit `metric_logged` events.
- Emit `experiment_finished` or `experiment_failed`.
- Emit `evaluation_created`.

### Acceptance criteria

- A command like this works:

```bash
python backend/scripts/run_one_experiment.py examples/tiny_cnn/mission.yaml
```

- It produces `events.jsonl` with mission, proposal, diff, metrics, result, and evaluation.

## Milestone 4: Autonomous loop

### Goal

Run multiple experiments autonomously.

### Tasks

- Implement deterministic heuristic planner first.
- Implement budget loop.
- Track best experiment.
- Generate next proposal based on previous results.
- Add simple evaluator and decider.
- Stop after max experiments.

### Heuristic planner ideas

Start with a sequence of safe changes:

1. baseline
2. lower LR
3. AdamW + weight decay
4. dropout increase
5. cosine scheduler
6. augmentation on

Then add LLM planning later.

### Acceptance criteria

- The loop can run 3-5 experiments without UI.
- The event log shows a trajectory with parent/child links.
- At least one experiment improves over baseline or is marked rejected.

## Milestone 5: Frontend static replay

### Goal

Render an existing `events.jsonl` in the UI.

### Tasks

- Build event reducer in frontend.
- Render mission top bar.
- Render trajectory graph with React Flow.
- Render event stream.
- Selecting a node updates the details panel.
- Show basic metric chart.
- Show diff text.

### Acceptance criteria

- Loading a sample events file shows a graph.
- Clicking nodes shows hypothesis, metrics, diff, and verdict.

## Milestone 6: Live event stream

### Goal

Connect the UI to the running backend mission.

### Tasks

- Add `GET /missions/{id}/stream` SSE endpoint.
- Frontend subscribes to SSE.
- Graph updates live as events arrive.
- Event stream panel updates live.
- Metrics chart updates live.

### Acceptance criteria

- Start mission from UI.
- Watch experiment events appear live.
- See a node go from proposed to running to finished.

## Milestone 7: LiteLLM planner

### Goal

Replace or augment heuristic planner with provider-agnostic LLM planning.

### Tasks

- Add LiteLLM dependency.
- Add model/provider settings.
- Implement structured planner prompt.
- Validate JSON output.
- Add fallback to heuristic planner on invalid output.

### Acceptance criteria

- User can configure provider/model/API key.
- Planner returns valid experiment proposals.
- Bad model output does not crash the loop.

## Milestone 8: Fork from node

### Goal

Add the main steering control.

### Tasks

- Add fork button in ExperimentDetails.
- Add ForkDialog with human instruction.
- Backend endpoint `POST /missions/{id}/fork`.
- Emit `fork_created`, `branch_created`, and `constraint_added`.
- Planner proposes next experiment from fork context.
- Tiny CNN fork can run live.

### Acceptance criteria

- User selects an experiment and forks it.
- New branch appears in graph.
- Human instruction appears in decision/constraint panel.
- A new experiment can run from the fork.

## Milestone 9: modded-nanogpt replay/import

### Goal

Create serious demo replay.

### Tasks

- Run or partially run modded-nanogpt experiments.
- Capture logs, metrics, diffs, notes.
- Convert into Kun events.
- Create replay file under `examples/replays/`.
- Ensure UI can show richer trajectory.

### Acceptance criteria

Replay includes:

- baseline
- 15+ experiment nodes if possible
- 2+ improvements
- 2+ failures or instability events
- at least one throughput/runtime tradeoff
- learned constraints
- forkable branch
- best run

## Milestone 10: Polish

### Goal

Make the demo feel like a product.

### Tasks

- Improve visual hierarchy.
- Add statuses/colors/icons.
- Add empty states.
- Add sample missions.
- Add one-click demo launch.
- Add pitch copy in app.
- Optionally wrap in Electron/Tauri.

### Acceptance criteria

- A judge can understand the product without much narration.
- Demo path is reliable.
- App looks intentional and polished.

## Suggested 48-hour schedule

### Hours 0-4

- Scaffold repo.
- Define event schema.
- Build JSONL writer.
- Build tiny CNN training script.

### Hours 4-8

- One-experiment runner.
- Metrics parser.
- Basic evaluator.
- First real `events.jsonl`.

### Hours 8-14

- Multi-experiment loop.
- Basic FastAPI endpoints.
- Static UI from sample events.

### Hours 14-22

- React Flow graph.
- Details panel.
- Metrics chart.
- Diff viewer.
- Event stream.

### Hours 22-30

- SSE live updates.
- Start mission from UI.
- LiteLLM planner.
- Fallback planner.

### Hours 30-36

- Fork from node.
- Learned constraints sidebar if time.
- Replay loader.

### Hours 36-42

- modded-nanogpt replay/import.
- Polish serious replay.
- Demo data shaping.

### Hours 42-48

- UI polish.
- Reliability fixes.
- Demo script rehearsal.
- Backup recordings/screenshots.

## Risk management

### Risk: LLM planner is flaky

Mitigation:

- deterministic fallback planner
- strict JSON schema validation
- config-only patching for tiny CNN

### Risk: training is slow

Mitigation:

- Fashion-MNIST instead of CIFAR-10
- small subset option
- short epochs/steps
- CPU-compatible fallback

### Risk: modded-nanogpt setup is hard

Mitigation:

- timebox setup to 60-90 minutes
- use replay/import path
- create semi-synthetic event log if real run is partial
- do not depend on live modded-nanogpt run

### Risk: UI takes too long

Mitigation:

- static event replay first
- graph + detail panel before fancy layout
- shadcn/ui for fast components

### Risk: too many features

Mitigation:

- one intervention only: fork from node
- no W&B integration
- no desktop wrapper until core works

## MVP definition of done

Kun MVP is done when:

1. A Fashion-MNIST mission can run multiple experiments autonomously.
2. Each experiment emits structured events.
3. The UI shows live graph/events/metrics/diffs/details.
4. A saved replay can be loaded.
5. A user can fork from a prior node with a constraint.
6. The demo can show a serious modded-nanogpt-style trajectory.
