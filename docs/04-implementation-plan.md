# Kun Implementation Plan

> **Reconciled with [`00-spec.md`](00-spec.md) (canonical v4; wins on any conflict).** Deltas: **UI before the trainer** (schema + open contract + emit helper + hand-authored sample `events.jsonl`, then cockpit UI, THEN tiny CNN trainer); the **LLM is the driver from the start** (not heuristic-first); **two modes — Mode A (Kun drives) and Mode B (Kun observes/steers an external loop)** with a Mode-B feedback channel (`GET /missions/{id}/state`); the **code patcher** has two implementations — `config-patch` (P0) and **`agent-edit`** (P1: orchestrate Claude Code/Codex to edit real model code); **live fork execution, approval gate, mid-run `instruct`, and commit-per-node are core (P1)** with the new events `instruction_added`/`experiment_approved`/`experiment_rejected`; **LiteLLM is IN** (provider-agnostic planning + a minimal per-mission model picker — only the elaborate settings UI stays out) and powers **model benchmarking + cross-model compare (P2)**; ship the **open logging contract + ~5-line `kun_log` emit helper** as a first-class deliverable and demonstrate an **independent external loop ingesting live** (DoD); emit `operator` (draft/debug/improve), `valid`/`buggy` statuses, `schema_version` (doc 03); **research-memory panel + compare view are CORE**; budget/stop emit `mission_finished`; **nanogpt prefers a recorded Kun-driven (Mode-A + `agent-edit`) run**, with external-session→convert as the fallback (honesty guard either way); everything is tagged **P0/P1/P2** with build gates (don't start P1 until the P0 spine demos end-to-end; don't start P2 until P1 steering works).

## Build philosophy

Build the event log + open logging contract + emit helper first; the UI is a projection of the event log and comes **before the trainer** (the trainer just prints metrics). Desktop packaging comes last, if at all.

The correct order is:

```text
P0: event schema (+deltas) + open contract + emit helper
  -> hand-authored rich sample events.jsonl
    -> cockpit UI (graph + node-view quad + memory panel + event stream + topbar)
      -> tiny CNN trainer + one-experiment runner (config-patch)
        -> LLM-driven loop + budget/stop + closed constraint loop (hero)
          -> live SSE + visual fork + replay
P1: agent-edit patcher (orchestrate Claude Code/Codex on real code)
  -> live fork execution + approval gate + mid-run instruct
    -> Mode-B feedback channel + commit-per-node
      -> recorded Mode-A-on-real-code (nanogpt) run -> serious replay
P2: LiteLLM model picker + benchmarking + cross-model compare
  -> demo polish
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

- Define Pydantic models for core events. Include `schema_version`, `operator` (draft/debug/improve), the v4 steering events `instruction_added`/`experiment_approved`/`experiment_rejected`, and map `experiment_finished`→`valid` / `experiment_failed`→`buggy` in the state builder (per doc 03).
- Implement JSONL append writer.
- Implement event id/timestamp assignment.
- **Ship the engine-agnostic open logging contract (documented JSONL format, doc 03) + a ~5-line `kun_log(...)` emit helper as a first-class deliverable** — any producer (external agent, script, human) is an equal citizen, not just Kun's loop.
- Implement `GET /missions/{id}/events`.
- Implement state builder that derives experiments and metrics from events.
- Add a hand-authored rich sample events file (the UI builds against this before the trainer exists).

### Acceptance criteria

- Can append events to `runs/<mission_id>/events.jsonl`.
- Can reload a mission from JSONL.
- Can derive a mission state object with experiments/metrics.
- An external script (not Kun's loop) can emit valid events via `kun_log(...)` and they render in the cockpit.

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
- Patch the per-experiment workspace via the patcher interface — `config-patch` (P0: write changed keys); `agent-edit` is the P1 implementation (Milestone 8b).
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

- Implement the LLM-driven planner as the primary path (via LiteLLM — the mission's `model` id + provider env key): given base node + mission state + accumulated memory, the LLM produces the hypothesis AND the actual change + rationale + evaluation. Emit `operator` (draft/debug/improve).
- Implement the heuristic planner as fallback/baseline (used on schema-validation failure and as a no-key demo/benchmark control).
- Implement budget/stop conditions: max_experiments, max_runtime_per_experiment_sec, optional target_metric_reached; on first hit, emit `mission_finished` with the best node.
- Track best experiment.
- Generate next proposal based on previous results.
- Add evaluator and decider (LLM-driven evaluation; map outcomes to `valid`/`buggy`).

### Heuristic planner ideas

Start with a sequence of safe changes:

1. baseline
2. lower LR
3. AdamW + weight decay
4. dropout increase
5. cosine scheduler
6. augmentation on

(The LLM is the driver from the start — the sequence above is only the heuristic *baseline/fallback*, not the primary planner.)

### Acceptance criteria

- The loop can run 3-5 experiments without UI.
- The event log shows a trajectory with parent/child links.
- Proposals emit an `operator` (draft/debug/improve); failed runs surface as `buggy` nodes, successful as `valid`.
- The loop terminates on a stop condition and emits `mission_finished` with the best node.
- At least one experiment improves over baseline or is marked rejected.

## Milestone 5: Frontend static replay

### Goal

Render an existing `events.jsonl` in the UI.

### Tasks

- Build event reducer in frontend.
- Render mission top bar (status: best metric, budget used, mode [A-live / B-observe / replay / paused], runtime, model).
- Render trajectory graph with React Flow (nodes badged by `operator`, colored by `valid`/`buggy` status — buggy = red).
- Render event stream.
- Selecting a node updates the details panel.
- Show basic metric chart.
- Show diff text (react-diff-viewer, not Monaco).
- Add the node-view quad: detail / diff / leaderboard / **compare** (diff two nodes' configs + overlay their metric curves).
- Add the **research-memory panel** (mission-wide accumulated constraints/learnings) — core.

### Acceptance criteria

- Loading a sample events file shows a graph (operator badges, valid/buggy coloring).
- Clicking nodes shows hypothesis, metrics, diff, and verdict.
- Compare view diffs two nodes and overlays their metric curves.
- Research-memory panel renders mission-wide accumulated constraints.

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

## Milestone 7: Harden the LLM planner (LiteLLM, provider-agnostic)

### Goal

Make the LLM-driven planner (the driver, introduced in Milestone 4) robust and **provider-agnostic via LiteLLM**. LiteLLM is IN — it powers the minimal per-mission model picker and model benchmarking (P2, §8 Beat 5). Only the elaborate provider/model/key **settings UI** (temperature/test-connection chrome) is out.

### Tasks

- Use **LiteLLM** for provider-agnostic planning; the model id comes from the mission spec (`model` field), key via env var. No elaborate settings UI.
- Implement the structured planner prompt (returns `operator` + hypothesis + changes + rationale).
- Validate JSON output (strict schema) with retry.
- Fall back to the heuristic planner/baseline on invalid output or no key.

### Acceptance criteria

- Planner runs provider-agnostically via LiteLLM, selecting the mission's `model` id; no elaborate settings UI required.
- Planner returns valid experiment proposals (incl. `operator`).
- Bad model output does not crash the loop (graceful fallback to heuristic baseline).

## Milestone 8: Fork from node

### Goal

Add the main steering control.

### Tasks

- Add fork button in ExperimentDetails.
- Add ForkDialog with human instruction.
- Backend endpoint `POST /missions/{id}/fork`.
- Emit `fork_created`, `branch_created`, and `constraint_added`.
- Planner proposes next experiment from fork context.
- Tiny CNN fork **executes a real run live** (Mode A) — fork is live execution, not visual-only.

### Acceptance criteria

- User selects an experiment and forks it.
- New branch appears in graph.
- Human instruction appears in decision/constraint panel.
- A new experiment **runs live** from the fork (Mode A); in Mode B it is queued via the feedback channel.

## Milestone 8b: `agent-edit` patcher (P1)

Add the second patcher implementation alongside `config-patch`. Hand the LLM's proposed change to a coding agent (Claude Code / Codex) run as a subprocess to edit *real model code*; return the diff; run train/eval on the patched workspace; emit `file_diff_created` with the real diff. Sandbox edits to the per-experiment workspace. Live-demo only on a fast target; show real-code Mode A as a recorded run (Milestone 9). This is what lets Kun autoresearch any model, not just config knobs.

## Milestone 8c: Approval gate + mid-run instruct (P1)

Pause-on-proposal: approve / reject / edit a proposed experiment before it runs — emit `experiment_approved` / `experiment_rejected`. Mid-run `instruct` box injects NL guidance — emit `instruction_added` — that biases the next proposal without forking. (New events per doc 03 deltas.)

## Milestone 8d: Mode-B feedback channel + commit-per-node (P1)

Add `GET /missions/{id}/state` returning active constraints + pending fork/instruct, so an external (Mode-B) loop polls at the top of each iteration and obeys — turning Mode-B steering from advisory into real. Add commit-per-node: each accepted node is a `git commit` on a per-trajectory branch (local, no GitHub API); store the sha on the node; pairs with `agent-edit`.

## Milestone 9: modded-nanogpt replay/import

### Goal

Create serious demo replay.

### Tasks

- **Prefer a recorded Kun-driven (Mode-A + `agent-edit`) run** on nanogpt (overnight on GPU per doc 07) — "Kun drove this itself." **Fallback:** a real EXTERNAL modded-nanogpt session (Claude Code / Codex + markdown harness, or a partial real run) converted via the open contract. Credibility comes from real artifacts either way.
- Capture logs, metrics, diffs, notes.
- For the fallback path, convert artifacts into Kun events via the open contract (incl. `operator` + `schema_version`); narrate exactly what happened — Kun-driven vs ingested — never imply live execution that didn't occur (honesty guard). *(The independent-external-loop wedge proof is now Demo Beat 2 — a ~15-line non-Kun script — separate from this milestone.)*
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

## Milestone 11: Model benchmarking + cross-model compare (P2)

Run the same mission under N models via LiteLLM + a minimal per-mission model picker (no elaborate settings UI). Add the cross-model compare view that ranks models as autoresearchers (hypothesis quality, sample-efficiency, time/cost to target). This is Demo Beat 5; drop first if time is tight.

## Suggested 48-hour schedule

> Indicative effort, not strict sequence. Canonical ordering is spec §9 (**UI before the trainer**; ship the open contract + ~5-line emit helper + a hand-authored sample `events.jsonl` first).

### Hours 0-4

- Scaffold repo.
- Define event schema (incl. `schema_version`, `operator`, `valid`/`buggy`).
- Build JSONL writer.
- Ship the open logging contract + ~5-line `kun_log` emit helper + a hand-authored rich sample `events.jsonl`.

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

- React Flow graph (operator badges, valid/buggy coloring).
- Details panel.
- Metrics chart.
- Diff viewer (react-diff-viewer).
- Compare view + leaderboard.
- Research-memory panel.
- Event stream.

### Hours 22-30

- SSE live updates.
- Start mission from UI.
- Harden the LLM planner (**LiteLLM, provider-agnostic**; minimal model picker).
- Heuristic fallback/baseline planner.

### Hours 30-36

- `agent-edit` patcher (P1).
- **Live** fork execution (P1, Mode A).
- Approval gate + mid-run instruct (P1).
- Mode-B feedback channel + commit-per-node (P1).
- Research-memory panel (core): mission-wide accumulated constraints + closed constraint loop.
- Replay loader.

### Hours 36-42

- Recorded Kun-driven (Mode-A + `agent-edit`) nanogpt run -> serious replay (external-convert fallback).
- Polish serious replay.
- Demo data shaping.
- (P2, droppable first) LiteLLM model picker + model benchmarking + cross-model compare.

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

- respect the P0→P1→P2 gates (spec §9); a finished P0 + half of P1 beats ten half-built features
- no W&B integration
- no desktop wrapper until core works

## MVP definition of done

Kun MVP is done when:

1. A Fashion-MNIST mission runs multiple experiments autonomously (LLM-driven proposals), emitting structured events, and terminates on a budget/stop condition (`mission_finished`). *(P0)*
2. The cockpit shows a live trajectory graph + node detail + metrics + diff + compare + event stream + research-memory panel, driven entirely by the event log. *(P0)*
3. A saved replay loads and is fully inspectable. *(P0)*
4. An **independent external producer** (a non-Kun ~15-line script using `kun_log`) emits **live** and renders in real time — proving the add-on/wedge. *(P0)*
5. A user forks/instructs/approves on a live mission; a constraint enters the memory panel and **deterministically** reshapes the next proposal (bound-violating proposals hard-rejected). *(P0 constraint loop; P1 live exec)*
6. **Kun drives real-code autoresearch via `agent-edit`** on at least one model (recorded is fine for the heavy one). *(P1)*
7. The serious run (Beat 1) shows a rich real trajectory (improvement, failure, best node). *(P0/P1)*
8. *(P2)* Two models are benchmarked as autoresearchers in the cross-model compare view.
9. A judge understands in ~1 minute that this is neither run-tracking nor agent-tracing, but a steerable, pluggable research **runtime + cockpit**.
