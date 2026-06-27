# Kun Demo Plan

## Demo objective

The demo should make one idea obvious:

> Kun does not just track ML runs or agent traces. Kun tracks and controls the autonomous research trajectory.

## Final demo structure

Use three paths:

1. **Serious recorded run**: modded-nanogpt replay.
2. **Reliable live run**: Fashion-MNIST tiny CNN.
3. **Fork/steering**: fork from a prior node, ideally shown on both replay and live path.

## Opening line

> W&B shows experiment runs. Agent observability shows traces. Kun shows the autonomous research trajectory: why each experiment happened, what changed, what evidence came back, and where a human can steer next.

## Demo Path A: modded-nanogpt replay

### Purpose

Credibility. This shows Kun matters for serious ML workflows.

### Setup

Open a saved mission:

```text
Mission: modded-nanogpt optimization replay
Objective: reduce steps/time to target validation loss
Mode: replay
```

### What to show

1. Trajectory graph with many experiments.
2. Baseline node.
3. Successful branch.
4. Failed/unstable branch.
5. Code/config diff.
6. Loss curve.
7. Throughput/runtime tradeoff.
8. Learned constraint.
9. Agent rationale card.

### Narration

> This is a recorded autonomous optimization session. Each node is not just a run. It is a hypothesis-backed experiment with a parent, a diff, metrics, evidence, and a decision.

Click a successful node:

> Here the agent tested a scheduler change. Kun shows the hypothesis, the exact diff, the validation loss curve, and the verdict. The important part is provenance: we can see why this branch exists.

Click a failed node:

> This run failed due to instability. Instead of being buried in logs, the failure becomes part of the research memory. The system learned a constraint that high learning rates in this region are risky.

Show learned constraints:

```text
Learned constraints:
- LR above threshold caused instability in multiple runs.
- Cosine scheduling improved convergence on the best branch.
- One optimizer tweak improved loss but hurt throughput.
```

## Demo Path B: fork from serious replay

### Purpose

Show Kun is a cockpit, not a passive dashboard.

### Action

Select a promising node and click **Fork**.

Human instruction:

```text
Keep the scheduler from this run, but avoid the learning-rate range that caused instability.
```

### Narration

> I can fork the research trajectory from any prior experiment. This is different from just comparing runs: Kun lets me steer the next branch using what the system learned.

Expected UI result:

- new branch appears
- fork event appears in stream
- human constraint appears in constraints/evidence panel
- proposed next experiment appears or is queued

## Demo Path C: live tiny CNN run

### Purpose

Proof that Kun can actually run autonomous loops live.

### Setup

Create or open mission:

```text
Mission: Fashion-MNIST CNN Accuracy Sprint
Objective: maximize validation accuracy
Budget: 3-6 experiments
Allowed changes: learning_rate, optimizer, dropout, batch_size, conv_channels, augmentation, scheduler
```

### Action

Click **Start Mission**.

Expected sequence:

```text
mission_started
experiment_proposed
file_diff_created
experiment_started
metric_logged
metric_logged
experiment_finished
evaluation_created
decision_created
```

### Narration

> The replay showed a rich serious session. This one is running live. The agent proposes a hypothesis, edits the config, launches training, streams metrics, evaluates the result, and updates the trajectory.

Click the newly created node:

> This node contains the full story: hypothesis, config diff, validation accuracy, runtime, and verdict.

## Demo Path D: live fork on tiny model

### Purpose

Prove fork is not just visual.

### Action

Select the best tiny CNN experiment and fork:

```text
Fork from this run, keep AdamW, but reduce dropout because the model may be underfitting.
```

Click **Run Fork**.

Expected result:

- new branch appears
- new proposed experiment appears
- config diff is generated
- command runs live
- metrics stream

### Narration

> This is the same steering mechanism, but now executing live on the tiny model. The human is not micromanaging every run; they are shaping the research trajectory.

## Closing line

> The core object in Kun is not a run and not a trace. It is the research trajectory: replayable, inspectable, and steerable.

## Backup demo if live training fails

If live loop fails during judging:

1. Open a pre-recorded Fashion-MNIST event log.
2. Show replay works.
3. Trigger fork UI without executing.
4. Explain that the run loop is the same event path and show logs/terminal if needed.

Backup narration:

> This saved session was produced by the same runner. The app treats live mode and replay mode identically because both are driven by the event log.

## Demo data requirements

### modded-nanogpt replay should contain

- baseline
- 15-30 experiment nodes if possible
- at least 2 successful improvements
- at least 2 failed/unstable experiments
- at least 1 learned constraint
- at least 1 throughput/runtime tradeoff
- code/config diffs
- loss curves
- final best run

### tiny CNN live demo should contain

- baseline
- 2-5 experiments
- at least one config diff
- val accuracy metrics
- one evaluator verdict
- one forkable node

## Judge Q&A answers

### Is this a W&B replacement?

No. W&B is excellent for run tracking. Kun sits above run tracking: it records the autonomous research process that creates the runs. It can integrate with W&B later.

### Is this just agent observability?

No. Agent observability tracks prompts, calls, tools, and traces. Kun tracks research-native objects: hypotheses, experiments, diffs, metrics, failures, evidence, decisions, and branches.

### Does the loop actually run experiments?

Yes. The tiny CNN mission runs live. The modded-nanogpt mission is a recorded serious trajectory for reliability and credibility.

### Why not run modded-nanogpt live?

The product can adapt to serious repos, but judging demos should not depend on expensive long-running GPU jobs. We show the serious trajectory from a recorded run and demonstrate the live loop on a fast model.

### What is the main technical contribution?

The evented research trajectory: a replayable and forkable representation of autonomous ML experimentation.

## One-minute version

> Kun is mission control for autonomous ML experiments. You define a goal, such as improving validation accuracy or reducing time-to-target-loss. The agent proposes experiments, edits config/code, runs training/evals, parses metrics, and decides the next branch. Kun records every step as a research trajectory. You can inspect the hypothesis, diff, metrics, evidence, and verdict for every experiment, replay the session later, and fork from any prior node with a new constraint.
