# CONTRACT.md — frozen cross-subagent contract for the P0 build

> This is the shared, **stable** interface every P0 subagent (backend / cockpit / loop)
> builds against. Source of truth: `docs/03-event-schema.md` (events) + `docs/00-spec.md`
> (canonical) + `docs/04-implementation-plan.md` (endpoints). **Do not change the event
> schema, endpoint names, or the sample path unilaterally — route any change through the
> lead/orchestrator** so the other streams don't break. If this file and doc 03 ever
> disagree, doc 03 wins; fix this file.

---

## 0. Frozen anchors (memorize these)

| Anchor | Value |
|---|---|
| Event contract | `docs/03-event-schema.md` |
| Emit helper | `kun/log.py` → `kun_log(event_type, payload, **envelope)` (already exists; ~5 lines) |
| Sample replay (build UI against this first) | `examples/replays/sample.events.jsonl` (already exists) |
| Independent-producer wedge proof | `examples/external_loop_demo.py` (already exists) |
| Per-mission event log | `runs/<mission_id>/events.jsonl` |
| Per-experiment workspace | `runs/<mission_id>/<experiment_id>/` (config.yaml, metrics.jsonl, stdout/stderr) |
| Events env var | `KUN_EVENTS` (path the emit helper appends to; default `events.jsonl`) |

---

## 1. Event envelope (every event)

```json
{
  "schema_version": 1,
  "event_id": "evt_000123",
  "timestamp": "2026-06-27T20:15:42.123Z",
  "type": "experiment_started",
  "mission_id": "mission_abc",
  "experiment_id": "exp_004",
  "branch_id": "branch_main",
  "parent_experiment_id": "exp_003",
  "payload": { }
}
```

- **Required:** `schema_version` (int, =1 for MVP), `event_id`, `timestamp` (ISO-8601 UTC),
  `type`, `mission_id`, `payload`.
- **Optional:** `experiment_id`, `branch_id`, `parent_experiment_id`, `actor`.
- `actor` = `{"type":"agent","name":"planner","model":"<litellm-id>"}` or
  `{"type":"human","name":"user"}`.
- The emit helper auto-fills `schema_version`, `event_id`, `timestamp`. Producers pass
  `type`, `payload`, and the envelope ids.

---

## 2. P0 event types (the only ones P0 must produce/consume)

Build for these. The v4 steering events (`instruction_added`, `experiment_approved`,
`experiment_rejected`) and the Mode-B feedback channel are **P1 — out of P0 scope**, but
keep the state builder tolerant of unknown types (ignore, don't crash).

| type | key payload fields (see doc 03 for full examples) |
|---|---|
| `mission_created` | `name`, `goal`, `objective{metric,direction,target}`, `budget{max_experiments,max_runtime_per_experiment_sec}`, `adapter`, `editable_files`, `allowed_changes[]`, `constraints[]` |
| `mission_started` | `mode` (`live`\|`replay`), `started_by` |
| `branch_created` | `name`, `reason`, `source` (+ envelope `branch_id`, `parent_experiment_id`) |
| `constraint_added` | canonical constraint object (see §3) — `source:"human"` |
| `experiment_proposed` | `operator` (`draft`\|`debug`\|`improve`, **required**), `hypothesis`, `changes{}`, `expected_outcome`, `risk`, `rationale` |
| `file_diff_created` | `file_path`, `base_file_path`, `diff` (unified diff string) |
| `experiment_started` | `command`, `workspace_path`, `timeout_sec` |
| `command_output` | `stream` (`stdout`\|`stderr`), `text` (optional; concise) |
| `metric_logged` | `name`, `value`, `step`, `epoch?`, `phase?` |
| `experiment_finished` | `status:"success"`, `final_metrics{}`, `artifacts[]` |
| `experiment_failed` | `failure_type` (e.g. `nan_detected`), `message`, `last_metrics{}`, `stdout_path?`, `stderr_path?` |
| `evaluation_created` | `verdict`, `summary`, `evidence[]`, `concerns[]` |
| `decision_created` | `decision` ∈ `{continue_branch,promote,reject,retry_debug,fork,stop}`, `rationale`, `next_action{}` |
| `constraint_learned` | canonical constraint object (see §3) — `source:"learned"` + `confidence`, `supporting_experiments[]` |
| `fork_created` | `instruction`, `reason` (+ envelope `branch_id`, `parent_experiment_id`, human `actor`) |
| `mission_finished` | `status`, `reason`, `best_experiment_id`, `best_metric{name,value}` |

---

## 3. Canonical constraint object (the hero loop depends on this)

`constraint_added` (human) and `constraint_learned` (learned) share ONE shape that the
research-memory panel renders and the planner enforces:

```json
{
  "constraint_id": "learned_002",
  "source": "human | learned",
  "text": "learning_rate > 0.004 caused unstable training in 2 experiments.",
  "applies_to": ["learning_rate"],
  "bound": {"param": "learning_rate", "op": ">", "value": 0.004},
  "confidence": "medium",                       // learned only
  "supporting_experiments": ["exp_002","exp_005"] // learned only
}
```

- **`bound` is what the planner HARD-REJECTS against.** Always include it for a numeric
  limit. The op is the *banned* direction (here `>` 0.004 means reject any proposal whose
  `changes.learning_rate > 0.004`).
- **Two memory tiers (same object):** a constraint **with** a `bound` is a *hard constraint*
  (deterministic hard-reject). A constraint **without** a `bound` is a *soft lesson* —
  prose/positive findings that only **bias** the planner prompt, never hard-reject. Both use
  this one object + the existing `constraint_added`/`constraint_learned` events (no new types).
  P0 ships the hard tier (NaN→LR rule); soft lessons + richer rules are P1 — see
  [doc 11](docs/11-research-memory-design.md). Keep the hard tier rule-derived; LLM-authored
  memory is soft-tier only.
- Closed-loop requirement (do not let it silently no-op): `experiment_failed` (NaN) →
  emit `constraint_learned` with a `bound` via a **deterministic rule** (NaN at lr=x →
  `{param:"learning_rate", op:">", value:x*0.5}`) → it enters mission state + the memory
  panel → the planner injects constraints into the prompt AND validation-rejects any
  proposed `changes` that violate a `bound` (retry) → the next `experiment_proposed`
  respects the bound and its `rationale` references the constraint.

---

## 4. Materialized experiment model (UI derives this from events)

```ts
type Experiment = {
  id: string;
  parentId?: string;
  branchId: string;
  operator?: "draft" | "debug" | "improve";
  status: "proposed" | "running" | "valid" | "buggy" | "promoted" | "rejected" | "forked";
  hypothesis?: string;
  rationale?: string;
  changes?: Record<string, unknown>;
  diff?: string;
  command?: string;
  metrics: MetricPoint[];          // from metric_logged
  finalMetrics?: Record<string, number>;
  verdict?: string;
  evidence?: string[];
  concerns?: string[];
};
```

**Status mapping (state builder):** `experiment_finished{status:"success"}` → node `valid`;
`experiment_failed` → node `buggy`; `decision_created{decision:"promote"}` → `promoted`;
`{decision:"reject"}` → `rejected`. Raw payloads keep `success`/`failed`/`nan_detected`;
`valid`/`buggy` is the node-lifecycle vocabulary the cockpit renders. Nodes are **badged by
`operator`** and **colored by status** (buggy = red).

---

## 5. HTTP surface (P0 only)

Base: FastAPI. **Pin these names.** (P1 endpoints listed only so you don't grab them now.)

| Method | Path | Purpose | Phase |
|---|---|---|---|
| `POST` | `/missions` | Create a mission (body = `mission_created` payload); emits `mission_created`. | P0 |
| `POST` | `/missions/{id}/start` | Start the Mode-A loop; emits `mission_started`. | P0 |
| `GET`  | `/missions/{id}/events` | Full event log (JSONL/array) for replay+reload. | P0 |
| `GET`  | `/missions/{id}/stream` | **SSE** — emit events as they're appended (live mode). | P0 |
| `GET`  | `/missions/{id}/experiments` | Materialized state (experiments + metrics) for initial hydrate. | P0 |
| `POST` | `/missions/{id}/fork` | Record a fork: emit `fork_created` + `branch_created` (+ `constraint_added` if a constraint was given). **P0 = record/visualize only; executing the forked run is P1.** | P0 |
| `POST` | `/missions/{id}/ingest` | Optional Mode-B intake: accept a raw event dict, fill envelope, append. (Alternatively, external producers append to `runs/<id>/events.jsonl` and the backend tails it for SSE — pick one and document it.) | P0* |
| `GET`  | `/missions/{id}/state` | Feedback channel (active constraints + pending fork/instruct). | **P1 — do not build** |

\* The wedge-proof DoD (external producer renders live) needs ONE working live-ingest path:
either `POST /ingest` or file-tail of `runs/<id>/events.jsonl`. Decide in Phase 0 and make
`external_loop_demo.py` exercise it.

---

## 6. Ownership boundaries (disjoint; enforce)

| Subagent | OWNS | Must not touch |
|---|---|---|
| **W1 backend/API** | `backend/app/api/**`, `backend/app/events/**`, `backend/app/state/**`, Pydantic event models | `web/**`, `backend/app/loop/**`, the schema (frozen) |
| **W2 cockpit UI** | `web/**` | `backend/**`, `examples/**` |
| **W3 trainer+loop** | `examples/tiny_cnn/**`, `backend/app/loop/**` (planner, patcher, runner, evaluator, constraint generator) | `backend/app/api/**`, `backend/app/events/**`, `web/**` |

Shared/frozen (change only via the lead): event schema (doc 03), the HTTP path names in §5,
the sample path, `kun/log.py`. The loop (W3) writes events **through the event log**
(`kun_log` / the events module), never by reaching into the API layer (W1).

---

## 7. Stack (pinned)

Vite + React + TypeScript · Tailwind + shadcn/ui · React Flow (graph) · Recharts (charts) ·
**react-diff-viewer** (NOT Monaco) · FastAPI + SSE · **JSONL only, in-memory state — NO
SQLite** · LiteLLM (provider-agnostic `propose(...)`) · Fashion-MNIST tiny CNN.

Tiny-CNN config knobs (doc 04 M2): `learning_rate, optimizer, batch_size, dropout,
conv_channels, weight_decay, augmentation, scheduler, epochs, seed`.

---

## 8. Phase-0 lead decisions (authoritative; added by orchestrator)

These resolve the open choices §5 left to Phase 0. Build against them.

### 8.1 Live-ingest = FILE-TAIL (the single live code path)

There is **one** live mechanism for BOTH modes: the backend tails
`runs/<mission_id>/events.jsonl` and pushes appended lines over SSE.

- **Per-mission log path is conventional:** `runs/<mission_id>/events.jsonl`. The
  state builder reads it; `/stream` tails it; replay reads the same file. Live and
  replay are literally the same bytes → satisfies "same event shape / same code path."
- **Mode A** (Kun's own loop, W3) appends via `kun_log(..., path=runs/<id>/events.jsonl)`.
- **Mode B** (external producer, Asset C) appends via `$KUN_EVENTS` pointed at
  `runs/<external_mission_id>/events.jsonl`, calling only `kun_log` — no HTTP, no
  backend import (keeps the wedge "obviously not Kun").
- We do **NOT** build `POST /missions/{id}/ingest` for P0. (Left for P1 if ever needed.)

### 8.2 External-mission registration entry point (additive endpoint, W1)

So an externally-produced log the backend never created still appears live:

`POST /missions/register` — body `{ "mission_id": "...", "events_path": "..."? }`.
Registers the mission id, defaults `events_path` to `runs/<mission_id>/events.jsonl`,
hydrates state from existing lines, and starts a tailer that streams new lines over the
normal `/stream` SSE. This is **additive** — it renames none of the frozen §5 paths.

- The cockpit (W2) gets a small "Observe external mission" affordance (enter a
  `mission_id`) that POSTs `/missions/register`, then opens `/stream`. A documented
  `curl` is the fallback so the demo never depends on the UI field.
- For the demo, `examples/external_loop_demo.py` writes to
  `runs/mission_external_demo/events.jsonl` (mission_id-consistent). The lead wires this
  during Phase 2; W3 does not touch it.

### 8.3 `kun/log.py` gains an optional `path=` kwarg (done in Phase 0, lead)

`kun_log(type, payload, path=..., **envelope)` — `path` overrides `$KUN_EVENTS` and
auto-creates the parent dir. External producers omit it (still the ~5-line surface);
the backend/loop pass `path=runs/<id>/events.jsonl`. **`kun_log` remains the single emit
helper everything uses** (non-negotiable). Do not append to JSONL by any other means.
