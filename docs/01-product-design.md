# Kun Product Design

## One-liner

**Kun is a mission-control cockpit for running, observing, replaying, and steering autonomous ML experiment loops.**

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
  A user-defined research objective with constraints, commands, metrics, budget, editable files, and model/provider settings.

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
   - provider/model config

2. **Autonomous experiment loop**
   - planner proposes next experiment
   - patcher edits config/code
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
   - for MVP, config diffs are enough for tiny CNN

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

Implement one strong intervention:

> **Fork from prior experiment with a human constraint.**

Example:

```text
Fork from exp_009.
Instruction: keep cosine scheduler, but avoid learning_rate > 0.003 because it caused NaNs.
```

The fork should create a new branch, emit events, ask the planner for a new proposal, generate a patch/config, and optionally run it.

## Nice-to-have features

Only add after the must-have loop and cockpit work.

- learned constraints / failed-ideas memory
- lightweight eval/regression panel
- human approval gate
- multi-agent swimlanes
- context compaction markers
- model comparison
- W&B import/export
- richer artifact viewer
- prompt/tool trace detail
- desktop shell via Electron or Tauri

The best nice-to-have is **learned constraints**, because it reinforces the research-native thesis.

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

The final demo has three paths:

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
- mode: live / replay / paused
- runtime
- model/provider

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
- success
- failed
- promoted
- rejected
- forked

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
