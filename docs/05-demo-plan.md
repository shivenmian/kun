# Kun Demo Plan

> **Reconciled with [`00-spec.md`](00-spec.md) §8 (canonical; wins on conflict).** v4 deltas: the demo is **FIVE beats** — (1) serious run on **real code** (prefer a **recorded Kun-driven, Mode-A + `agent-edit`** nanogpt run — *"Kun drove this itself"*; fallback = external Claude-Code/Codex run converted via Mode-B ingest), (2) **ingest a genuinely independent external loop** (the wedge: a ~15-line non-Kun script emitting live via `kun_log`), (3) reliable live Fashion-MNIST (Mode A, `config-patch`), (4) **steer it live** (approval gate + mid-run instruct + fork-with-constraint, all executing live in Mode A), (5) **model benchmarking (P2)** — same mission under two models, cross-model compare. Kun supports **Mode A (drives) and Mode B (observes)**. **LiteLLM is in** (powers benchmarking); **live fork executes** in Mode A; the approval gate + instruct are real controls. The **LLM is the driver** (genuine autoresearch, not a scripted sweep). The **research-memory panel + closed constraint loop is the hero feature**. Main contribution = the **open standard for autoresearch trajectories + the cockpit/runtime** (add-on, not replacement). Detailed narration below is preserved; Paths A/B/C/D map onto Beats 1/4/3/4.

## Demo objective

The demo should make one idea obvious:

> Kun does not just track ML runs or agent traces. Kun tracks and controls the autonomous research trajectory.

## Final demo structure

Use five beats:

1. **Serious run on real code** (credibility): a real autoresearch session on nanogpt that edits real training code. **Prefer** a recorded **Kun-driven (Mode-A + `agent-edit`)** run — *"Kun drove this itself."* **Fallback:** an external Claude-Code/Codex run whose real artifacts are converted (Mode-B ingest). Load as replay; walk the trajectory; start a fork to show the mechanism.
2. **Ingest a genuinely independent external loop** (the wedge): a trivial, obviously-not-Kun ~15-line script that imports `kun_log` and emits a few experiments **live** → its nodes appear in the cockpit in real time. Decoupled from the nanogpt run, so the wedge proof doesn't depend on the GPU job.
3. **Reliable live run**: Fashion-MNIST tiny CNN, Mode A, `config-patch`, driven by Kun's own LLM loop.
4. **Steer it live**: on the live tiny-CNN mission, hit the approval gate (reject/edit a proposal), mid-run **instruct**, and **fork with a constraint** — the constraint enters the research-memory panel and deterministically reshapes the next proposal. All execute live because it's Mode A.
5. **Model benchmarking (P2, optional)**: same mission under two models → cross-model compare view ranks them *as autoresearchers*. Drop first if time is tight.

(The detailed "Path A/B/C/D" sections below predate this and map onto the beats: Path A → Beat 1; Path B fork-on-replay → the fork shown on the Beat 1 replay; Path C → Beat 3; Path D → Beat 4 live. Beat 2 and Beat 5 are detailed separately.)

## Opening line

> This is how people steer autonomous ML runs today — ~100 manual interventions in a markdown file (Prime Intellect's auto-nanogpt, May 2026). Kun runs the loop, shows you the reasoning, lets you steer it — and any loop can plug in. W&B shows the runs; agent observability shows traces; Kun shows the autonomous research trajectory — it runs and steers the autoresearcher, and is the open standard those trajectories are logged in: why each experiment happened, what changed, what evidence came back, and where a human can steer next.

## Demo Path A: modded-nanogpt replay

### Purpose

Credibility. This shows Kun matters for serious ML workflows — and that Kun can *drive* real-code autoresearch, not just observe it.

**Prefer:** a recorded **Kun-driven (Mode-A + `agent-edit`)** session on nanogpt that edited *real training code* — *"Kun drove this itself."* **Fallback:** an external agent (Claude Code/Codex + a markdown harness, or a partial real run) whose **real artifacts** are converted into Kun's event format (Mode-B ingest). Either way credibility comes from a rich real trajectory (≥1 real improvement, ≥1 real failure/NaN, a clear best/forkable node).

**Honesty guard:** narrate exactly what happened — Kun-driven (Mode A) vs ingested (Mode B), and recorded vs live. If it was a recorded Kun-driven run, say "Kun drove this itself, recorded overnight"; if ingested, say so. Never imply live execution that didn't occur, and don't claim the fork/branch executed live if it didn't.

### Setup

Open a saved mission:

```text
Mission: modded-nanogpt optimization (recorded)
Objective: reduce steps/time to target validation loss
Adapter: modded_nanogpt   Patcher: agent-edit
Source mode: A (Kun-driven, recorded)  [fallback: B (ingested/converted)]
Load as: replay
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

## Demo Beat 2: ingest an external loop

### Purpose

Prove Kun is an add-on/cockpit for *any* loop, not a closed tool — the wedge.

### Narration

> This isn't Kun's loop, and it isn't the nanogpt run. It's 15 lines of someone else's script — five of them are `kun_log` calls — emitting live right now. Watch its nodes appear in the cockpit. Kun is observing a loop it never ran. That's the bet: the open standard for autoresearch trajectories, and the cockpit on top.

Show the emit helper / contract and the same artifacts re-framed to highlight the contract.

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
- proposed next experiment is **queued** here only because this is a *recorded* nanogpt trajectory we don't re-run live (Beat 1). The fork mechanism itself **executes live** in Mode A — shown on the tiny CNN in Beat 4. (In Mode B, fork is advisory until the external loop reads Kun's state back via the feedback channel.)

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

Prove the cockpit has teeth: approval gate, mid-run instruct, and fork all execute live (Mode A).

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

> This is the full steering surface, executing live on the tiny model. I can stop a proposal at the **approval gate** and reject or edit it before it runs; I can **instruct** mid-run ("try cosine") to bias the next proposal; and I can **fork with a constraint** ("ban dropout > 0.4") — the constraint enters the research-memory panel and the next run is deterministically reshaped (bound-violating proposals hard-rejected). The human is not micromanaging every run; they are shaping the research trajectory.

## Demo Beat 5: model benchmarking (P2, optional)

### Purpose

Show Kun can compare models *as autoresearchers*, not just compare runs. Drop first if time is tight.

### Action

Run the same mission (same goal, budget, adapter) under two models (e.g., Claude vs GPT) via the per-mission model picker (LiteLLM), then open the **cross-model compare view**.

### Narration

> Same mission, two different models driving the loop. Kun ranks them as researchers — hypothesis quality, sample-efficiency, time and cost to target. The question isn't "which model writes better code," it's "which model is the better autoresearcher." That's a view only a trajectory-level tool can give you.

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

No. W&B is excellent for run tracking. Kun sits above run tracking: it records the autonomous research process that creates the runs. Kun is an add-on, not a replacement — you can point Kun's own loop at your model (Mode A) *or* instrument whatever you already run (W&B included) in ~5 lines (Mode B) and get the trajectory cockpit on top. Future bet: it's the open standard the whole autoresearch ecosystem logs into.

### Is this just agent observability?

No. Agent observability tracks prompts, calls, tools, and traces. Kun tracks research-native objects: hypotheses, experiments, diffs, metrics, failures, evidence, decisions, and branches.

### Does the loop actually run experiments?

Yes — and in two modes. **Mode A: Kun drives.** Kun's own loop is the autoresearcher (planner → patcher → runner → parser → evaluator → decider); the tiny CNN mission runs live this way. The LLM is the *driver*, not a narrator: given the base node + mission state + accumulated memory, it generates the hypothesis AND the actual change, then reads results and evaluates — genuine LLM-driven autoresearch (AIDE/Weco-style), not a pre-scripted sweep. Crucially, via the **`agent-edit` patcher** (Kun orchestrating Claude Code/Codex as a subprocess to edit real code), Kun can drive autoresearch on *any* model's real training code — e.g. nanogpt optimizer/attention changes — not just config knobs. **Mode B: Kun observes/steers** an external loop that emits via `kun_log`. The serious nanogpt run is preferably a **recorded Kun-driven (Mode-A `agent-edit`)** trajectory — "Kun drove this itself," recorded for reliability; an external-session-converted run (Mode B) is the fallback. A heuristic planner exists only as a validation fallback/baseline.

### Why not run modded-nanogpt live?

Because an `agent-edit` → train → eval cycle on real code is minutes-long and nondeterministic, and judging demos shouldn't hinge on expensive GPU jobs. So we show real-code Mode A as a **recorded Kun-driven run** (Kun drove it overnight via `agent-edit`), and demonstrate the live loop with `config-patch` on a fast model. Same event path either way.

### What is the main technical contribution?

The open standard for autoresearch trajectories, plus the cockpit **and runtime** on top. The trajectory is an evented, replayable, forkable representation — but the contribution isn't a novel algorithm (forking/constraints/node-graphs aren't new). It's ecosystem position: a dead-simple engine-agnostic logging contract (`kun_log(...)`, ~5 lines) that any loop — Claude Code, Codex, a script, or Kun's own — emits into and gets the cockpit on top. Won the way LangSmith/OpenTelemetry won agent observability: by being the thing you both *instrument your existing loop with* (Mode B) **and** *run your research on* (Mode A). An add-on, not a replacement.

## One-minute version

> Kun is mission control for autonomous ML experiments. You define a goal, such as improving validation accuracy or reducing time-to-target-loss. The agent proposes experiments, edits config/code, runs training/evals, parses metrics, and decides the next branch. Kun records every step as a research trajectory. You can inspect the hypothesis, diff, metrics, evidence, and verdict for every experiment, replay the session later, approve/reject proposals, instruct mid-run, and **fork from any prior node with a constraint that reshapes the next run live** — and any external loop can plug into the same cockpit in ~5 lines.
