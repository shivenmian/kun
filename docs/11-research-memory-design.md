# Research-Memory Design (P1 enrichment)

> **Status:** the **P0 hard tier shipped** (deterministic NaN→LR bound + hard-reject — the hero
> loop, spec §4). This note specs the **P1 enrichment** that makes memory richer than "what the
> human typed + one NaN rule." Canonical scope owner: spec §7 (P1). Like [doc 08](08-agent-edit-design.md)
> for `agent-edit`, this is the design-before-code note for memory. **Read before building P1 memory.**

## The problem with P0 memory

Today the research-memory panel is one-dimensional:

- **Negative-only** — it stores banned regions (`bound`s), never "what worked."
- **NaN-triggered-only** — the sole automatic generator is `learn_constraint_from_nan` (NaN at
  `lr=x` → ban `learning_rate > x*0.5`). Underfitting, repeated regressions, throughput tradeoffs,
  and softer lessons never enter memory automatically. (The sample replay's `learned_002`
  "dropout > 0.4 underfits" is **hand-authored** — the live loop cannot currently produce it.)
- **Static** — each NaN emits a fresh `learned_NNN`; constraints are never merged, confidence never
  grows, nothing decays.

So outside human input, memory barely "learns." This note fixes that **without weakening the
deterministic spine that makes the hero beat reliable.**

## Design principle: two tiers

Keep every memory entry in one of two tiers. This is the invariant that lets us add intelligence
(even LLM-authored) without ever letting the loop silently no-op.

| Tier | What it holds | Enforced how | May be LLM-authored? |
|---|---|---|---|
| **Hard constraints** | structured `bound`s (banned regions) | **hard-reject filter** (`violates_bound`) — deterministic | **No** — must stay rule-derived |
| **Soft lessons** | prose / positive findings ("cosine helped +0.012", "lr sweet spot ≈ [0.003,0.006]") | injected into the planner **prompt** to *bias* the next proposal | **Yes** — it only nudges, can't force a bad run |

Both tiers reuse the **existing canonical constraint object** (CONTRACT §3) and the existing
`constraint_added` / `constraint_learned` events — **no envelope/schema change, no new event types**.
A soft lesson is simply a `constraint_learned` with **no `bound`** (CONTRACT §3: a no-`bound`
constraint can never hard-reject — it's bias-only). State stays reconstructable from the event log.

## Enrichment items (ordered by value-per-effort)

### 1. More deterministic learned rules — *hard/soft tier* — closes the sample↔live gap
Add pure, unit-tested generators in `backend/app/loop/constraints.py`, fired from `run_mission.py`:
- **Underfitting** (hard): regularization ↑ **and** train_acc drops with val → ban e.g. `dropout > x`.
  This is literally the sample's `learned_002`, which the live loop currently can't emit.
- **Repeated regression** (soft): a param value that underperforms across ≥2 experiments → a
  cautionary prose lesson (no bound).
Risk: low. Preserves "cannot no-op." Makes a live run as rich as the replay.
**Acceptance:** a live mission with an underfit experiment surfaces a second *learned* constraint;
new unit tests cover each generator's trigger + boundary.

### 2. Positive memory / Σ-summaries — *soft tier* — biggest narrative upgrade
On every `promote` with a real metric delta, auto-record a one-line lesson ("cosine: +0.012") and
**inject it into the planner prompt** alongside the bans. This is AIDE's per-node Σ-summary rolled
into mission memory — it turns the panel from a blocklist into a research notebook, and the planner
visibly builds on prior wins. Effort: moderate.
**Acceptance:** after a promoted improvement, the panel shows a positive lesson and a later
proposal's rationale references it.

### 3. Memory hygiene (merge + confidence growth) — cheap polish, big "it's learning" feel
Merge constraints on the same param (tighten the bound, append `supporting_experiments`) and **raise
`confidence` as evidence accumulates** (1 supporting experiment = medium, ≥2 = high) instead of
emitting duplicate `learned_NNN`. Memory visibly consolidates over a run. Effort: low.
**Acceptance:** two NaNs on the same param produce **one** sharpened constraint, not two; confidence
rises.

### 4. LLM "memory writer" — *soft tier, additive* — highest ceiling, gate it
A periodic LLM pass that distills durable lessons from the trajectory (the spec's "softer lessons").
Powerful but nondeterministic, so it is **purely additive on top of 1–3** and may write only soft
lessons (never hard bounds). If it flakes or returns junk, the loop is unaffected. Gated like
`agent-edit`: build only after 1–3 are solid.

### 5. (Stretch, P2) Richer expressiveness
Conditional / interaction constraints ("`lr>0.01` unstable **only when** `scheduler=none`"),
categorical bans (`optimizer != sgd`), and UI causation arrows ("proposal reshaped by `learned_002`").
Schema impact: would extend the `bound` shape — coordinate via the lead (CONTRACT §3 is frozen).

## Build order & recommendation

**1 + 3 first** (both deterministic; together they make a *live* run match the sample's richness and
feel like it learns), **then 2** (the narrative jump), **gate 4**, defer 5 to P2. Slot into the P1
sequence right after `compare` (pure-craft, low-risk) and before/parallel with the heavier
`agent-edit` work.

## Invariants to preserve (do not break)

- The **deterministic hard tier cannot no-op** — the NaN→bound→hard-reject path stays rule-based and
  unit-tested; LLM memory is *only ever additive* (soft tier).
- **Same canonical constraint object** (CONTRACT §3); reuse `constraint_added`/`constraint_learned`;
  **no new event types**; state remains reconstructable from the JSONL event log.
- **Per-mission only** — cross-mission / persistent memory stays out of MVP (JSONL + in-memory, spec
  §3/§13). Revisit post-hackathon (spec §12).
