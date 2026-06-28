# Kun Product Design

> **Reconciled with [`00-spec.md`](00-spec.md) (canonical; wins on any conflict).** v4 deltas applied/relevant here: Kun supports **both Mode A (Kun drives the loop) and Mode B (Kun observes/steers an external loop)** — Mode A is the powerful one; LLM is the *driver* of the loop (not heuristic-first, not a narrator); **LiteLLM is back in** — it powers model benchmarking (a P2 demo beat) + provider-agnostic planning, exposed via a *minimal* per-mission model picker (no elaborate settings UI); the code patcher has two implementations — **`config-patch` (P0)** and **`agent-edit` (P1, orchestrates Claude Code/Codex to edit real model code so Kun can autoresearch any model, not just config knobs)**; **live fork execution, mid-run instruct, and a human approval gate are core (P1)** — not visual-first/stretch; SQLite cut (JSONL + in-memory only); learned-constraints/**research-memory panel** and **compare-two-experiments** are **core**; node statuses are `valid`/`buggy` and nodes are badged by `operator` (draft/debug/improve); the demo is now **five beats** (serious run on real code, independent external producer, live tiny CNN, live steering, model benchmarking [P2]) (see spec §8 / doc 05); the **wedge/moat** is the open engine-agnostic logging contract + ~5-line emit helper — Kun is an **add-on, not a replacement** for your loop; everything is tagged **P0/P1/P2**; diff viewer is react-diff-viewer (not Monaco).

## One-liner

**Kun is a mission-control cockpit for running, observing, replaying, and steering autonomous ML experiment loops — and the open standard those trajectories are logged in. Any loop (Claude Code, Codex, a script, or Kun's own) plugs in via a ~5-line emit helper.**

## Product thesis

Autonomous ML research is moving from one-off scripts to long-running agentic experiment loops. These loops can propose hypotheses, edit code/configs, run training/evals, interpret metrics, learn from failures, and iterate for hours.

The current tooling stack does not give researchers a first-class interface for this workflow.

- Experiment trackers show runs, params, metrics, artifacts, and comparisons.
- Agent observability tools show prompts, tool calls, traces, costs, and latencies.
- AutoML/HPO tools search parameter spaces and schedule trials.

Kun focuses on a different primitive: the **research trajectory**.

A research trajectory captures:

- why each experiment exists
- what hypothesis the agent was testing
- what code/config changed
- which metrics/evals/failures came back
- what evidence the agent used
- what branch was promoted, rejected, or forked
- what the system learned and should avoid
- where a human intervened
- how the trajectory can be replayed or recovered later

## Positioning

### Short pitch

> W&B shows experiment runs. Agent observability shows traces. Kun shows the autonomous research trajectory: hypotheses, diffs, metrics, failures, decisions, branches, and steering controls.

### Longer pitch

> Kun is a mission-control layer for autonomous ML experimentation. A researcher defines a mission, such as improving validation accuracy or reducing steps-to-target-loss. Kun runs an autoresearch-style loop that proposes experiments, modifies config/code, launches training/eval commands, parses metrics, evaluates outcomes, and decides the next branch. The cockpit renders every action as a live, replayable research trajectory so the human can inspect, fork, constrain, and recover the work.

## Product name

Product name: **Kun**

Working subtitle: **Mission Control for Autonomous ML Experiments**

## Target user

Primary hackathon target:

- ML engineers and research hackers experimenting with autonomous training/eval loops.
- People who understand W&B, sweeps, training curves, and agentic coding/research loops.

Broader future users:

- AI research teams running long-lived experiment agents.
- ML platform teams building internal autoresearch infrastructure.
- Agent framework builders who need ML-native experiment observability.
- Model/agent eval teams running automated iteration over prompts, policies, finetunes, and evaluations.

## Core object model

Kun should be organized around these nouns:

```text
Mission
  A user-defined research objective with constraints, commands, metrics, budget, and editable files. (The `model` is a LiteLLM model id, chosen via a *minimal* per-mission model picker — no elaborate settings UI.)

Trajectory
  The full history of autonomous research work inside a mission.

Branch
  A path through the trajectory. Branches can come from agent decisions or human forks.

Experiment
  A single attempted change/run/eval, represented as a node in the trajectory graph.

Hypothesis
  The agent's stated reason for the experiment.

Evidence
  Metrics, evals, failures, diffs, logs, artifacts, and comparisons used to judge the experiment.

Decision
  The agent or human verdict: promote, reject, fork, retry, stop, or continue.

Constraint
  A learned or human-provided rule that shapes future experiments.
```

## Final hackathon scope

Kun runs in **two modes**: **Mode A**, where Kun drives the loop itself (planner → patcher → runner → parser → evaluator → decider — steering has teeth because Kun owns execution), and **Mode B**, where Kun observes/steers an external loop that emits via `kun_log` (steering is advisory unless the external loop reads Kun's state back via the feedback channel). Mode A is the powerful one.

### Must-have: execution layer

Kun should actually run autonomous loops, not merely visualize a log.

Required execution features:

1. **Mission spec**
   - goal
   - objective metric
   - direction: maximize/minimize
   - budget
   - train/eval command
   - editable files
   - metric parser
   - constraints
   - patcher: `config-patch` (P0) or `agent-edit` (P1)
   - model (LiteLLM model id, via a minimal per-mission model picker)
   - adapter (tiny_cnn | modded_nanogpt | custom)

2. **Autonomous experiment loop**

   The LLM is the *driver*: given the base node + mission state + accumulated memory, it proposes the hypothesis AND the actual change (params/code) and evaluates the result. The heuristic planner is a schema-validation fallback and offline/no-key baseline only — not the primary path.

   - LLM planner proposes next experiment (hypothesis + concrete change)
   - patcher applies the change — **`config-patch`** (P0: writes changed keys into a config file) or **`agent-edit`** (P1: orchestrates a coding agent — Claude Code / Codex — to edit *real model code*, so Kun can autoresearch any model, not just config knobs)
   - runner launches training/eval
   - metrics parser reads metrics
   - evaluator judges result
   - decider chooses next action

3. **Experiment runner**
   - runs actual commands
   - captures stdout/stderr
   - enforces timeout/budget
   - writes command/result events

4. **Metrics parser**
   - supports metrics JSONL or metrics file for the tiny CNN path
   - supports stdout/log conversion for the modded-nanogpt replay path

5. **Evaluator/verdict**
   - promotes/rejects/fails/inconclusive
   - attaches human-readable rationale

6. **Budget and stop condition**
   - max experiments
   - max runtime per experiment
   - optional target metric reached condition

### Must-have: observability layer

Required cockpit features:

1. **Live event stream**
   - shows the autonomous loop doing real work

2. **Trajectory graph**
   - nodes are experiments
   - edges are decisions/branches
   - selected node drives all detail panels

3. **Metrics chart**
   - primary metric over time
   - optional secondary metric such as runtime or throughput

4. **Code/config diff viewer**
   - exact changes made by the agent
   - config diffs cover the P0 tiny-CNN path; **`agent-edit` (P1) produces real code diffs** (`file_diff_created`), and commit-per-node (P1) yields real git diffs for free

5. **Experiment detail panel**
   - hypothesis
   - parent experiment
   - changed params/files
   - command
   - metrics
   - artifacts/logs
   - verdict

6. **Decision/rationale cards**
   - why the experiment was proposed
   - what evidence supported/rejected it
   - what the agent learned

7. **Replay from saved session**
   - load JSONL event logs
   - reconstruct mission/trajectory/experiments
   - support the serious modded-nanogpt replay

### Must-have: control layer

The cockpit ships multiple real interventions (all give it teeth because in **Mode A** Kun owns execution):

- **Stop / pause** (P0).
- **Fork-from-node with a human constraint (P1)** — in Mode A the fork **executes a real run** (live fork execution is core, not visual-only).
- **Approval gate (P1)** — pause-on-proposal: approve / reject / edit a proposed experiment *before* it runs (emits `experiment_approved` / `experiment_rejected`).
- **Mid-run `instruct` (P1)** — inject NL guidance (`instruction_added`) that biases the next proposal.

Example fork:

```text
Fork from exp_009.
Instruction: keep cosine scheduler, but avoid learning_rate > 0.003 because it caused NaNs.
```

The fork creates a new branch, emits events, asks the planner for a new proposal, generates a patch/config, and **executes the run in Mode A** (in Mode B it queues an instruction via the feedback channel).

## Nice-to-have features

Only add after the must-have loop and cockpit work.

- lightweight eval/regression panel
- multi-agent swimlanes
- context compaction markers
- W&B import/export
- richer artifact viewer
- prompt/tool trace detail
- desktop shell via Electron or Tauri

**Note (v2):** learned constraints are no longer a nice-to-have — the **research-memory panel** (mission-wide accumulated constraints) is now a *core* surface, and the closed loop (failure → learned constraint → reshapes the next proposal) is the hero demo beat. See spec §6/§7. Likewise the **human approval gate** is now core (P1), and **model benchmarking + cross-model compare** are in scope as the **P2** second demo story; **compare-two-experiments** is a core view (spec §6/§7/§8 Beat 5).

Example:

```text
Learned constraints:
- LR > 3e-3 caused NaNs twice.
- Dropout > 0.4 underfit.
- Cosine schedule improved 3 of 4 branches.
- Optimizer tweak improved loss but reduced throughput.
```

## Explicit non-goals for hackathon

Do not build:

- full W&B replacement
- fully general agent framework
- arbitrary repo support that works perfectly
- complex distributed GPU orchestration
- full GPU scheduler
- deep context editing
- perfect multi-model scheduler
- full finetuning platform
- full eval platform
- huge dashboard suite
- live leaderboard-beating modded-nanogpt run during judging

## Demo strategy

**Superseded by spec §8 (canonical): the demo is now FIVE beats** — (1) serious run on **real code** (prefer a **recorded Kun-driven** Mode-A + `agent-edit` run; fallback is an external session → convert, with an honesty guard), (2) ingest a genuinely independent external loop (the wedge), (3) live Fashion-MNIST tiny CNN (Mode A, `config-patch`), (4) steer it live (approval gate / instruct / fork with constraint), (5) model benchmarking across models (P2, droppable). The paths below are retained as detail and map onto those beats; see doc 05.

The original framing had three paths:

### Path A: serious recorded run

Use a saved modded-nanogpt-style optimization trajectory to prove Kun matters for real ML workflows.

Show:

- many experiment nodes
- successful branches
- failed branches
- optimizer/scheduler/code diffs
- loss curves
- throughput/runtime tradeoffs
- learned constraints
- agent rationale
- fork from prior node

### Path B: reliable live run

Use a tiny Fashion-MNIST CNN mission to prove Kun can actually run an autonomous loop live.

Show:

```text
Create mission
-> agent proposes experiment
-> config changes
-> command runs
-> metrics stream
-> evaluator returns verdict
-> graph updates
```

### Path C: fork/steering

Use both if possible:

- modded-nanogpt replay fork for visual credibility
- tiny CNN fork for live execution credibility

## UX layout

### Left sidebar

- Missions
- Branches
- Experiments
- Saved replays

### Top bar

Show:

- mission name
- best metric
- current experiment
- budget used
- mode: A-live / B-observe / replay / paused
- runtime
- model (the mission's LiteLLM model id)

### Center

Primary view: **research trajectory graph**.

Nodes should include:

- experiment id
- short hypothesis
- metric delta
- status

Node statuses:

- baseline
- proposed
- running
- valid
- buggy
- promoted
- rejected
- forked

Nodes are also badged by **operator** (`draft` / `debug` / `improve`). Status vocabulary matches doc 03 (`valid` = ran & produced a metric; `buggy` = failed/NaN — the `debug` operator targets these).

### Right panel

When an experiment node is selected:

- hypothesis
- rationale
- changed params
- diff viewer
- metric chart
- verdict
- evidence
- fork button

### Bottom or side stream

Live event stream:

```text
Agent proposed hypothesis
Edited config.yaml
Started exp_004
val_accuracy = 0.873
Detected overfitting gap
Rejected branch
Learned constraint
```

## Product quality bar

The MVP is successful if a judge can understand, within one minute:

1. Kun runs autonomous ML experiment loops.
2. Each experiment is represented as a hypothesis-backed node.
3. They can inspect what changed and why.
4. They can see metrics/evidence and decisions.
5. They can replay/fork the trajectory.
6. This is different from run tracking and different from generic agent tracing.
