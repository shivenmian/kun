# Kun Build Spec (Canonical)

> This is the tightened, post-audit source of truth. Where it conflicts with docs 01–07, **this wins**.
> Docs 01–07 remain as detail/reference. Read this first.
>
> **Changelog:** v2 — promoted the engine-agnostic logging contract from de-risk to *the core wedge/moat*; LLM is the driver (not a narrator); added budget/stop, mission-spec fields, research-memory panel, compare-experiments view, stop/pause, topbar status; disambiguated the nanogpt run as external-session→convert; added a 4th demo beat (ingest an external loop); mandated event-schema deltas (now patched into doc 03).
> **v3** — specified the closed constraint loop (canonical constraint object with a structured `bound` + deterministic hard-reject so the reshape fires *visibly*); inlined the emit helper and made Beat 2 a genuinely independent producer (moat = demonstrated, not asserted; decoupled from GPU risk); specified the nanogpt→events converter; defined the heuristic fallback, the `decision` enum, and the topbar model source.
> **v4** — Kun supports **both Mode A (drives) and Mode B (observes)** with per-mode steering semantics + a Mode-B feedback channel; added the **code patcher** (`agent-edit`: orchestrate Claude Code/Codex to edit real model code) so Kun can autoresearch *any* model, not just config knobs; promoted **live fork execution, mid-run instruct, and a human approval gate** to core; pulled in **model benchmarking** (+ LiteLLM) and **cross-model compare**; nanogpt can now be a *recorded Kun-driven (Mode-A) run*; tagged everything **P0/P1/P2**; expanded §12 into a comprehensive deferred backlog to revisit post-hackathon.
> **v5** — execution-discipline pass (**no scope added, nothing deleted**): made **craft-first** the operating principle (for the demo, cockpit polish is the moat you can actually win; "open standard" stays the long-term framing — §2 unchanged); split time-safety into two valves — a **graceful drop-order** and an independent **`agent-edit` risk gate** (§9); moved the **`compare`** view P0 → P1 so the P0 craft budget concentrates on the graph + research-memory panel + closed constraint loop.

---

## 1. What Kun is

Kun is a **flight recorder, cockpit, and runtime for autonomous ML research trajectories** — and the **open standard those trajectories are logged in**.

> W&B shows the runs. Kun shows the autonomous researcher that created them — and lets you run and steer it.

An agent is given a research goal; it proposes hypotheses, edits code/config, runs training/evals, reads results, learns, and decides what to try next. Today that loop lives in scripts, TUI sessions, scattered logs, git diffs, and tracker runs. Kun gives it a first-class cockpit: a **forkable research trajectory** of hypotheses → diffs → metrics → failures → decisions → learned constraints → human steering.

Kun does this in **two modes** (§4): it can **drive** the loop itself (Mode A) or **observe/steer** an external loop (Mode B). Either way it's an **add-on to the autoresearch ecosystem** — you can point Kun's own loop at your model, *or* instrument your existing loop (Claude Code, Codex, a script) in ~5 lines and get observability, memory, tractability, and steering on top.

## 2. Positioning & the wedge

Kun is built for the world where **autoresearch loops dominate ML experimentation/training**. We are not waiting for that world to fully arrive; we are building the canonical surface for it.

- Run-centric (W&B/MLflow), trace-centric (LangSmith/Weave/Phoenix/Braintrust), and trial-centric (Optuna/Ray Tune) tools all exist and are good at their jobs. None expose the **autonomous researcher's evolving decision process**.
- "This is already starting" footnote (not the foundation): Prime Intellect's `auto-nanogpt` (May 2026) ran agents on the nanoGPT speedrun and needed ~100 human interventions steered through a markdown file. That is the workflow Kun replaces — but the pitch stands on the future bet, not on present-day pain.

**The wedge (this is the moat):** *the open standard for autoresearch trajectories + the best cockpit/runtime for them.* None of the underlying mechanics (forking, constraints, node graphs, time-travel) are novel anywhere — nor is Karpathy-style autoresearch itself. That's fine. The defensibility is **ecosystem position**, won the way LangSmith/OpenTelemetry won agent observability: by being the thing you *instrument your existing system with* (Mode B) and *run your research on* (Mode A), not by a novel algorithm.

This only holds if Kun is a **true add-on**. The fork in the road:
- If Kun can only observe missions *Kun itself* runs → it's a walled garden competing with however you already do autoresearch. Weak.
- If any loop can emit Kun's trajectory format in ~5 lines and get the cockpit → Kun becomes the layer the whole ecosystem logs into. That's the win.

So the bar is: **it works, it's coherent, it's the obvious thing a researcher reaches for, and any loop can plug into it.** Competitors copying it is not the threat; becoming a closed demo nobody can plug their real loop into is.

Secondary, softer moat = **taste/integration**: the opinionated trajectory model (typed operators + accumulated memory + fork + compare) being genuinely good. Earned, not defended — also sufficient for our bar.

## 3. Architecture & the open trajectory contract

**Event log is the single source of truth.** Append-only JSONL → state builder → UI projection. Live mode and replay mode use the same path.

**The open logging contract is a first-class deliverable, not an internal detail — it is the wedge from §2.** Make "log a trajectory node" a dead-simple, **engine-agnostic** contract: a documented JSONL event format (doc 03) plus a tiny emit helper (`kun_log(...)`, ~5 lines to wire in). Every producer is an equal citizen: Kun's own loop, an overnight nanogpt run, a human, Claude Code, Codex, or any future agent. The UI works even if a given producer is half-built, and — more importantly — Kun can observe loops it didn't run.

```
producers (Kun's own loop [Mode A] | external agent: Claude Code/Codex [Mode B] | script | human)
  └─► kun_log(...) ──► events.jsonl   (append-only, source of truth, the open contract)
        └─► state builder ──► (constraints/fork/instruct readable back out — Mode-B feedback, §4)
              └─► cockpit UI (live via SSE, or static replay — same code path)
```

### The emit helper (the moat artifact — keep it ~5 lines)

This is the entire contract surface an external loop needs. It must stay tiny.

```python
# kun/log.py
import json, time, uuid, os

def kun_log(event_type, payload, **envelope):
    rec = {"schema_version": 1,
           "event_id": "evt_" + uuid.uuid4().hex[:12],
           "timestamp": envelope.pop("timestamp", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
           "type": event_type, "payload": payload, **envelope}
    with open(os.environ.get("KUN_EVENTS", "events.jsonl"), "a") as f:
        f.write(json.dumps(rec) + "\n")
```

Wiring an existing loop in is then literally:

```python
from kun.log import kun_log
kun_log("experiment_proposed", {"operator": "improve", "hypothesis": ..., "changes": {...}},
        mission_id=MID, experiment_id=EID, parent_experiment_id=PID)
kun_log("experiment_finished", {"status": "success", "final_metrics": {...}},
        mission_id=MID, experiment_id=EID)
```

- The helper **auto-fills `event_id`, `timestamp`, `schema_version`** so an external producer needs to know nothing about Kun internals.
- Two equal paths: append to `$KUN_EVENTS` (file) **or** POST the same dict to `/missions/{id}/ingest` (the server fills the same envelope fields). Either way the producer is a first-class citizen.
- This file + the documented event types in doc 03 **is the entire "standard."** If it grows past a screen, that's scope creep (§11).

Stack: Vite React + React Flow + Recharts + react-diff-viewer (not Monaco) · FastAPI + SSE · JSONL only (**no SQLite for MVP**) · LiteLLM for provider-agnostic planning (powers benchmarking, §8 Beat 5).

## 4. The autonomous loop

### Two modes — Kun supports both (Mode A is the powerful one)

- **Mode A — Kun drives.** Kun's own loop *is* the autoresearcher: planner → **patcher** → runner → parser → evaluator → decider. Kun owns execution, so **steering has teeth**: fork executes, constraints bind, the approval gate blocks the next run. This is the powerful mode — lean into it.
- **Mode B — Kun observes/steers an external loop.** An external agent (Claude Code/Codex/script) is the autoresearcher and emits via `kun_log`. Kun is the cockpit + memory. Steering is *advisory* unless the external loop reads Kun's state back (feedback channel below).

Same event log, same UI, same cockpit for both. The mode is a property of who owns execution, not of the UI.

### Mission spec (the entry point — pin these fields; detail in doc 01)
`goal` · `objective_metric` · `direction` (max/min) · `budget` · `train/eval command` · `editable_files` / config knobs · `patcher` (`config-patch` | `agent-edit`) · `model` (LiteLLM model id) · `constraints` · `adapter` (tiny_cnn | modded_nanogpt | custom).

### The loop — two separate concerns, don't conflate them
- **The LLM drives proposal generation.** Given the selected base node + mission state + accumulated memory/constraints, the LLM produces the hypothesis **and the actual change** (params for config-patch; code edits for agent-edit), plus rationale and the post-run evaluation. This is genuine autoresearch — the LLM's judgment *is* the product, exactly like AIDE/Weco. **Do not cut this.**
- **The selection policy is deliberately dumb** (AIDE-style, no MCTS): *which* node to expand = keep drafting until N seeds → else debug buggy nodes within a bounded debug depth → else greedily `improve` the single best valid node. Human-overridable via fork/instruct/approval.

### The patcher — this is what makes Mode A powerful (P0 `config-patch` / P1 `agent-edit`)
The patcher applies the LLM's proposed change to a per-experiment workspace. One interface, two implementations:
- **`config-patch` (P0):** writes changed keys into a config file. Reliable, fast (seconds/cycle). Powers the tiny-CNN path and is the always-available fallback.
- **`agent-edit` (P1):** hands the proposed change to a **coding agent (Claude Code / Codex) run as a subprocess** to edit *real model code*, and returns the resulting diff. **This is what lets Kun autoresearch any model** (e.g., nanogpt — new optimizers, attention tweaks), not just config knobs. The runner then executes the train/eval command on the patched workspace; the parser reads the metric; emit `file_diff_created` with the real diff.
- **Risk (sequence it right):** an `agent-edit` → train → eval cycle on real code is **minutes and nondeterministic**. So: live-demo `agent-edit` only on a fast/small target, and show **real-code Mode A as a *recorded* run** (§8 Beat 1). Keep `config-patch` as the reliable fallback. Sandbox edits to the per-experiment workspace.

### Heuristic planner = fallback + baseline, not the primary path
Grid/random over the tiny-CNN knobs (lr, optimizer, dropout, scheduler) + canned hypothesis strings, **subject to the same constraint hard-reject filter**. Runs when LLM output fails schema validation and as an offline/no-key demo mode that can't hard-fail on stage. Also a useful benchmark control (LLM-driver vs heuristic).

### Budget, stop conditions & controls
- **Stop conditions:** `max_experiments`, `max_runtime_per_experiment_sec`, optional `target_metric_reached`. First hit terminates → emits `mission_finished` with the best node (the demo's "mission complete" beat).
- **Human controls (all give the cockpit teeth):**
  - **Stop / pause** (P0). *(Status: only the **automatic** budget/stop → `mission_finished` shipped in the P0 spine; the **human** stop/pause control was deferred and is carried into P1 steering — see §7 and [doc 12](12-p1-handoff.md).)*
  - **Approval gate (P1):** pause-on-proposal — approve / reject / edit a proposed experiment *before* it runs (emits `experiment_approved` / `experiment_rejected`). Completes the "cockpit, not autopilot" story.
  - **Fork-from-node with constraint (P1 live exec):** in Mode A the fork **executes a real run**; in Mode B it queues an instruction (see feedback channel).
  - **Mid-run `instruct` (P1):** inject NL guidance (`instruction_added`) that biases the next proposal — steering without forking.

### Steering teeth & the Mode-B feedback channel (P1)
- **Mode A:** fork → real run; approve/reject/edit before a run; `instruct` shapes the next proposal; constraints hard-reject violating proposals. All execute because Kun owns the loop.
- **Mode B feedback channel:** the external agent polls `GET /missions/{id}/state` (active constraints + pending fork/instruct) at the top of each iteration and obeys. ~10 lines on the producer side, same `kun_log` partnership. This is what turns Mode-B steering from *advisory* into *real* — steer in Kun's UI, the external loop's next move changes.

### The closed constraint loop (the hero feature — specify it, don't hand-wave) (P0)

A **constraint** is the canonical research-memory object (one shape; reconciles doc 03's `constraint_added`/`constraint_learned`):

```json
{"constraint_id": "c_001", "source": "human|learned",
 "text": "LR > 3e-3 caused NaNs twice",
 "applies_to": ["learning_rate"],
 "bound": {"param": "learning_rate", "op": ">", "value": 0.003},
 "confidence": "high", "supporting_experiments": ["exp_002", "exp_005"]}
```

The optional **structured `bound`** is what makes a "banned region" machine-checkable (not just prose). The loop closes **deterministically**:

1. A failure (`experiment_failed`, e.g. NaN) → **constraint generator** emits `constraint_learned`. For the demo-critical NaN→LR-ban case use a **deterministic rule** (NaN at LR=x → `bound: learning_rate > x*0.5`); LLM-generated text for softer lessons.
2. The constraint enters mission state and the **research-memory panel** (§6).
3. The planner reads accumulated constraints and **(a) injects them into the prompt** AND **(b) hard-rejects any proposal whose `changes` violate a structured `bound`** (validation-retry). The hard-reject makes the reshape **deterministic and visible on stage** — not a hope that the LLM "noticed."
4. The next `experiment_proposed` respects the bound and its `rationale` references the constraint — visible causation. *This is the hero beat; build it so it cannot silently no-op.*

**Memory tiers (P0 hard tier shipped; richer memory is P1 — see [doc 11](11-research-memory-design.md)).** Keep every memory entry in one of two tiers so intelligence can be added without ever letting the loop no-op: **hard constraints** (structured `bound`s, enforced by the deterministic hard-reject — rule-derived only) and **soft lessons** (prose/positive findings like "cosine helped +0.012", injected into the planner prompt to *bias*, may be LLM-authored). Both reuse the canonical constraint object and `constraint_added`/`constraint_learned` (a soft lesson is just a `constraint_learned` with no `bound`) — no schema change. P0 ships only the hard tier with the single NaN→LR rule; **P1 enrichment** adds more deterministic rules (e.g. underfitting bounds), positive Σ-summary lessons, and memory hygiene (merge + confidence growth). Today, outside human input, the only auto-learned memory is the NaN→LR bound.

### Decisions, selection policy & topbar
Each selection-policy branch emits a `decision_created` with `decision ∈ {continue_branch, promote, reject, retry_debug, fork, stop}` so the graph shows *why* each node was expanded. The topbar `model` string is the mission's LiteLLM model id.

**Kun's value-add sits on top of a real LLM-driven loop:** observability, research memory, tractability, replay, and steering — plus the ability to *run* the loop itself (Mode A).

## 5. Trajectory data model (borrowed from AIDE — arxiv 2502.13138)

A node = one experiment. Each node carries:

- **operator type**: `draft` (new approach from scratch) | `debug` (repair a failed node, preserve approach) | `improve` (exactly **one atomic change** to a valid node, so the metric delta is attributable)
- **status**: `proposed | running | valid | buggy | promoted | rejected | forked` (`valid` = ran & produced a metric; `buggy` = failed to run / NaN / errored → the `debug` operator targets these)
- hypothesis · the single diff (vs parent) · command · metrics · final metrics
- **Σ-summary**: structured per-node result = metrics + key params + a one-line learned hint *(per-node atom of the research memory; see §6)*
- parent edge (+ branch id) · optional **commit sha** (when commit-per-node is on, P1)

**Schema deltas (patched into doc 03):** `operator` on `experiment_proposed`; `valid`/`buggy` statuses; `schema_version` on the envelope; plus v4 events `instruction_added`, `experiment_approved`, `experiment_rejected`. Doc 03 is the shared subagent contract — backend and frontend must build against it so they don't drift.

### commit-per-node (P1)
Each accepted node is a `git commit` on a per-trajectory branch (local, no GitHub API). Makes "fork" literally `git branch`, yields real diffs for free, and pairs naturally with `agent-edit` (real code → real commits). Store the sha on the node.

## 6. Cockpit surfaces (UI)

- **Trajectory graph** (React Flow): nodes colored by status (buggy = red, etc.), badged by operator; selecting a node drives every panel. (Large-trajectory legibility — collapse/filter by status — is P1 nice-to-have if the nanogpt graph gets dense.)
- **Node view — P0 triad + P1 compare:** `detail` (hypothesis/rationale/code) · `diff` (unified diff vs parent) · `leaderboard` (results table sorted by metric) — these three are P0 · **`compare`** *(P1)* (diff two nodes' configs + overlay their metric curves — the most-wanted ML action; makes a large trajectory tractable).
- **Research-memory panel** (P0): the **mission-wide accumulated** constraints/learnings/banned-regions across the whole trajectory — the surface that embodies "memory" and makes the hero beat legible. A new learned constraint visibly enters this panel and then reshapes the next proposal. *(P1 enrichment, [doc 11](11-research-memory-design.md): also render positive Σ-summary lessons and rising confidence as evidence accumulates — turning the panel from a blocklist into a research notebook.)*
- **Cross-model / benchmarking view** (P2): the same mission run under N models side-by-side — compares them *as autoresearchers* (hypothesis quality, sample-efficiency, time/cost to target). See §8 Beat 5.
- **Steering controls:** fork dialog · approval gate (approve/reject/edit a pending proposal) · mid-run instruct box · stop/pause.
- **Topbar status:** mission name · best metric · current experiment · budget used · mode (A-live / B-observe / replay / paused) · runtime · model.
- **Event stream** (live via SSE).

## 7. Scope (with build priorities)

**P0 = demo-critical spine (build first). P1 = the power features that make it a cockpit, not a viewer. P2 = second demo story, droppable last.** If time compresses, the drop order is P2 → P1-stretch → never P0 (the precise order + the `agent-edit` gate are in §9).

> **Operating principle (craft-first).** The mechanics here are admittedly unnovel (§2); for the demo, the only edge winnable in the timeframe is **cockpit craft** — the graph, the research-memory panel, and the closed constraint loop *firing visibly*. Spend the hours there. The open-standard framing stays on the slide and is nearly free structurally (`kun_log` ~5 lines + the Beat-2 producer ~15 lines), so it does **not** trade against polish — but the heavy P1/P2 machinery does, which is why it's gated below.

### P0 — core (without these there is no product)
- Open logging contract + `kun_log` emit helper (§3) — the wedge.
- Event log + in-memory state builder + replay (same path as live).
- LLM-driven loop, **Mode A**, with `config-patch` patcher (tiny CNN).
- Closed constraint loop + research-memory panel (§4) — the hero feature.
- Trajectory graph + node-view **triad** (detail/diff/leaderboard) + event stream + topbar. *(`compare` moved to P1 — it's the soft-defer; the constraint loop, not compare, is load-bearing for the narrative.)*
- Budget/stop → `mission_finished`. Visual fork. Live SSE.

### P1 — power features (the reason it's a cockpit; build right after P0)
- **`compare` view** (moved from P0): diff two nodes' configs + overlay metric curves. Build first in P1 — it's pure cockpit craft and the most-wanted ML action.
- **Live fork execution** (Mode A).
- **Approval gate** + **mid-run `instruct`** + **Stop/Pause** (the human stop/pause control is tagged P0 in §4, but only the automatic budget/stop shipped in the P0 spine — build it here as part of steering; see [doc 12](12-p1-handoff.md)).
- **`agent-edit` patcher** — Kun autoresearches *real code* (the big power-up). **Gated (see §9): build only after the doc-08 spike passes; fall back to `config-patch` the instant a cycle flakes.** Highest wow-per-hour *if* it works, but it can't be demoed live and is the top scope-trap — treat it as the most droppable P1 item.
- **Mode-B feedback channel** (external loop reads back constraints/instructions → steering has teeth).
- **commit-per-node** (synergizes with `agent-edit`).
- **Research-memory enrichment** ([doc 11](11-research-memory-design.md)): make memory richer than "human input + one NaN rule" via a **two-tier** model (deterministic hard `bound`s + bias-only soft lessons). Sub-items, by value-per-effort: (1) more deterministic learned rules (e.g. underfitting → `dropout` bound, closing the sample↔live gap); (2) positive Σ-summary lessons in the prompt; (3) memory hygiene (merge constraints + grow confidence); (4) gated LLM "memory writer" (soft tier only). **Start here:** the underfitting→`dropout` bound (part of 1) + memory hygiene (3) — see [doc 11](11-research-memory-design.md). Low-risk, high narrative value — build early in P1 (after `compare`). Reuses the canonical constraint object; no schema change.
- Recorded **Mode-A-on-real-code** run for the serious demo (§8 Beat 1).

### P2 — second demo story (in scope, lowest priority; first to drop under time pressure)
- **Model benchmarking** (#9): run the same mission under N models, compare them as autoresearchers. Requires LiteLLM (in) + a minimal per-mission model picker (NOT an elaborate settings UI — no temperature/test-connection chrome) + the **cross-model compare view** (#18).

### Borrowed from AIDE/Weco (cheap, high realism — fold into P0/P1)
- Three typed operators, one atomic change per `improve`; buggy/valid states + bounded debug depth; Σ-style per-node summary; greedy expand-best policy; the detail/diff/leaderboard triad (P0) + `compare` (P1).

### Cut for MVP (see §12 backlog to revisit; §13 for hard non-goals)
- **SQLite / durable persistence** — JSONL + in-memory is enough.
- **Full GitHub PR integration**, **MCTS / sophisticated search**, **PR-citation lineage** — rabbit holes.
- Everything in §12 (deferred) and §13 (non-goals).

## 8. Demo (beats)

**Beat 1 — serious run on real code (credibility).** A real autoresearch session on nanogpt that *edits real training code*. **Prefer:** a **recorded Kun-driven (Mode-A + `agent-edit`) run** done overnight on **DigitalOcean GPU** (Plan A; 60–90 min setup timebox → Modal/Prime Intellect → partial-run+replay-shaping, per doc 07) — *"Kun drove this itself."* **Fallback:** an external agent (Claude Code/Codex + markdown harness) whose real artifacts are converted (Mode B ingest). Either way, load as **replay**, walk the trajectory/cards, and **start** a fork to show the mechanism.
- **Honesty guard:** narrate exactly what happened — Kun-driven vs ingested — and never imply live execution that didn't occur.
- **Rich trajectory, not a good score:** ≥1 real improvement, ≥1 real failure/NaN, a clear best/forkable node.
- **Converter (fallback path):** `modded_nanogpt` ingest maps artifacts → events (git diffs → `file_diff_created`; log metrics → `metric_logged`; final loss/throughput → `experiment_finished`; NaNs → `experiment_failed` + `constraint_learned`). If artifacts are messy, **hand-author the JSONL from real numbers** rather than writing a fragile parser under time pressure.

**Beat 2 — ingest a genuinely independent external loop (the wedge).** A **trivial, obviously-not-Kun** ~15-line script that imports `kun_log` and emits a few experiments **live** → its nodes appear in the cockpit in real time. *"This isn't Kun's loop. It's 15 lines of someone else's script; five of them are `kun_log` calls."* Shows "any loop plugs in" with **N=2** (one visibly foreign), and **decouples the wedge proof from the GPU run.** Commit and rehearse this script.

**Beat 3 — reliable live loop (proof it's real).** Live Fashion-MNIST tiny CNN, Mode A, `config-patch`. Propose → patch → train → parse → evaluate → emit → graph updates. CPU-compatible, pinned seed. *"Proof the loop runs live."*

**Beat 4 — steer it live (proof it's a cockpit).** On the live tiny-CNN mission: hit the **approval gate** (reject/edit a proposal), **instruct** ("try cosine"), and **fork with a constraint** ("ban dropout > 0.4") — the constraint enters the research-memory panel and **the next run is deterministically reshaped** (bound-violating proposals hard-rejected). This executes live because it's Mode A.

**Beat 5 — model benchmarking (P2, optional).** Same mission under two models (e.g., Claude vs GPT) → the cross-model compare view ranks them *as autoresearchers* (sample-efficiency, time-to-target). *"Which model is the better researcher?"* Drop first if time is tight.

**Opening narrative:** *"This is how people steer autonomous ML runs today — ~100 manual interventions in a markdown file. Kun runs the loop, shows you the reasoning, lets you steer it — and any loop can plug in."*

**Backup:** pre-recorded replays; same event path as live, so the app treats them identically.

## 9. Build order

```
P0: event schema (+deltas) + open contract + emit helper
  -> hand-authored rich sample events.jsonl
    -> cockpit UI on the sample (graph + node-view triad [detail/diff/leaderboard] + memory panel + event stream + topbar)
      -> tiny CNN trainer + one-experiment runner (config-patch)
        -> LLM-driven loop + budget/stop + closed constraint loop (hero)
          -> live SSE + visual fork + replay
P1: compare view -> research-memory enrichment (two-tier; doc 11) -> live fork execution + approval gate + mid-run instruct
  -> agent-edit patcher (orchestrate Claude Code/Codex on real code) [GATED — see below]
    -> Mode-B feedback channel + commit-per-node
      -> recorded Mode-A-on-real-code (nanogpt) run -> serious replay
P2: LiteLLM model picker + benchmarking + cross-model compare
  -> demo polish
```

UI before the trainer. The cockpit + contract are the deliverable; the trainer just prints metrics. **Do not start P1 until the P0 spine demos end-to-end; do not start P2 until P1's hero steering works.**

**Two independent time-safety valves (don't conflate them):**
1. **Graceful drop-order** — you've run low on time and everything built so far works. Drop in reverse build order, never touching P0: **benchmarking (P2) → commit-per-node → Mode-B feedback channel → approval gate + mid-run instruct → recorded nanogpt run → `compare`.** A finished P0 + a clean slice of P1 beats a sprawl of half-built features.
2. **`agent-edit` risk gate** — *independent of how much time is left.* Build `agent-edit` only after the doc-08 sanity spike passes (confirm the Claude Code flags, non-interactive editing, and timeout bounds). If the spike fails, or any later `agent-edit → train → eval` cycle flakes, fall back to `config-patch` immediately. Because it can't be demoed live (ships as a *recorded* run, §8 Beat 1) and is the top scope-trap, in practice it is often the first P1 thing abandoned — that's expected, not a failure.

**Minimum strong demo (the stop-point under time pressure):** the **P0 spine alone is a complete, thesis-proving demo** — a live tiny-CNN autoresearch loop, the **closed constraint loop** (failure → learned constraint → visibly reshapes the next proposal), the cockpit (graph + node detail + research-memory panel + event stream), the **~15-line independent-producer wedge proof**, and replay. If you ship only that, you still have a strong demo. P1 (esp. **`agent-edit` real-code autoresearch** — the highest wow-per-hour item *if its spike passes*; otherwise drop it without sentiment) raises the ceiling; P2 (benchmarking) is droppable. The `compare` view now sits at the front of P1 (moved out of P0): the closed constraint loop, not compare, is what's load-bearing for the narrative, so P0 craft concentrates on the graph + research-memory panel + the constraint loop firing visibly.

## 9b. Non-code assets (own these explicitly — they're on the critical path)

Three deliverables are not "features" but gate the demo. Assign them, don't let them slip.

- **Asset A — hand-authored rich sample `events.jsonl` (P0, author FIRST).** The entire P0 cockpit builds against this before any trainer exists; it's the fastest path to a thesis-complete replay. It must, on its own, tell the whole story: `mission_created` (tiny CNN) → ~6–10 experiments with `operator`s → ≥1 real improvement → ≥1 `buggy` (NaN) → a `constraint_learned` **with a structured `bound`** → a **subsequent proposal that visibly respects that bound** (the hero closed-loop, legible in replay) → a clear best node → a human `fork_created` + `constraint_added` → `mission_finished`. If this asset is good, you can demo the thesis with zero live code.
- **Asset B — the serious run → `events.jsonl` (P1, Beat 1).** Prefer a **recorded Kun-driven (Mode-A + `agent-edit`) nanogpt run**; fallback = external-session → convert. Full runbook + compute plan + timeboxes in [doc 07](07-modded-nanogpt-runbook.md). Must be a rich trajectory (≥1 improvement, ≥1 failure/NaN, clear best/forkable node). Honesty guard applies.
- **Asset C — the ~15-line independent producer script (P0, Beat 2).** Tiny, but it IS the wedge proof — an obviously-not-Kun loop calling `kun_log` live. Commit it and rehearse it; it's decoupled from the GPU run so it always lands.

The `agent-edit` patcher (the one component that needs design-before-code) is specified in [doc 08](08-agent-edit-design.md) — read it before starting P1.

## 10. Definition of done

1. A Fashion-MNIST mission runs multiple experiments autonomously (LLM-driven proposals), emitting structured events, and terminates on a budget/stop condition. *(P0)*
2. The cockpit shows a live trajectory graph + node detail + metrics + diff + event stream + research-memory panel, driven entirely by the event log *(P0)*; `compare` is added in P1.
3. A saved replay loads and is fully inspectable. *(P0)*
4. An **independent external producer** (a non-Kun ~15-line script using `kun_log`) emits **live** and renders in real time — proving the add-on/wedge. *(P0)*
5. A user forks/instructs/approves on a live mission; a constraint enters the memory panel and **deterministically** reshapes the next proposal (bound-violating proposals hard-rejected). *(P0 constraint loop; P1 live exec)*
6. **Kun drives real-code autoresearch via `agent-edit`** on at least one model (recorded is fine for the heavy one). *(P1)*
7. The serious run (Beat 1) shows a rich real trajectory (improvement, failure, best node). *(P0/P1)*
8. *(P2)* Two models are benchmarked as autoresearchers in the cross-model compare view.
9. A judge understands in ~1 minute that this is neither run-tracking nor agent-tracing, but a steerable, pluggable research **runtime + cockpit**.

## 11. Risk timeboxes
- **`agent-edit` cycle time** → an edit+train+eval on real code is minutes & nondeterministic: live-demo it only on a fast target; show real-code Mode A as a *recorded* run; keep `config-patch` as the reliable fallback.
- DigitalOcean GPU setup: **90 min hard** → fall back without sentiment (Modal/Prime Intellect → partial-run+replay-shaping).
- LLM planner flaky → strict JSON schema validation + retry; heuristic fallback/baseline keeps the loop alive.
- Benchmarking (P2) doubles run cost/time → keep it on the fast model only; drop first if time is tight.
- UI overruns → static replay first guarantees something to show.
- Scope creep on the contract → the emit helper is ~5 lines + a documented format; do not build an SDK.
- **Scope creep overall** → respect the P0 → P1 → P2 gates in §9. A finished P0 + half of P1 beats a sprawl of ten half-built features.

## 12. Deferred backlog (out of MVP — revisit post-hackathon)

> Single canonical list of everything cut *with intent to reconsider*. (Hard non-goals are §13.)

- **Durable persistence (SQLite/DB)** — when scale/multi-session needs it.
- **Full GitHub PR integration** + the **PR / human-gating output primitive** (agent node → branch → PR → human merge) — when Kun targets real shared repos.
- **PR-citation / cross-branch lineage** (credit when one branch builds on another) — matters multi-collaborator.
- **MCTS / smarter selection policy** — only if the dumb greedy policy proves limiting.
- **Eval / regression panel** — beyond the compare view.
- **Multi-agent swimlanes** — oversee N concurrent missions/agents in one view (strong as Kun scales).
- **Context-compaction markers** — show where an agent compacted its context.
- **W&B / MLflow import-export** — interop with incumbent trackers.
- **Richer artifact viewer** — sample images (e.g., misclassified Fashion-MNIST), checkpoints, attention maps.
- **Prompt/tool trace detail** — likely *integrate* with existing agent-observability tools rather than build (it's their lane).
- **Desktop shell** (Electron/Tauri) — packaging polish, never blocks the web app.
- **Large-graph navigation** (zoom/collapse/filter) — if trajectories routinely exceed ~30 nodes.

## 13. Non-goals (hard — keep out; scope-explosion traps)

Kun is **not**: a full W&B replacement · a full MLflow replacement · a generic LangSmith replacement · a generic arbitrary-repo agent framework (perfect support) · a production distributed GPU scheduler · a complex multi-model/multi-agent orchestration platform · a full finetuning platform · a full eval platform · a live modded-nanogpt leaderboard-beating system · deep context editing · a perfect multi-model scheduler · a huge dashboard suite.

(nanogpt *run/replay/convert* is in scope and required for Beat 1; nanogpt *winning the leaderboard* is not.)
