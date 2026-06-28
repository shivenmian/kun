# Kun Mode-A autonomous loop (W3)

The loop that *is* the autoresearcher: **planner → patcher → runner → (constraint
generator) → evaluator → decider**, emitting every event through `kun_log` to
`runs/<mission_id>/events.jsonl` in the same shape/order as
`examples/replays/sample.events.jsonl`.

## Setup

```bash
cd /Users/shivenmian/kun-w3
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt        # installs torch (CPU)
```

## Train once (the tiny CNN, standalone)

```bash
python examples/tiny_cnn/train.py --config examples/tiny_cnn/config.yaml
# writes metrics.jsonl next to the config; prints FINAL_METRICS or NAN_DETECTED.
# lr >= 0.02 reliably NaNs (exit 3); lr ~0.003-0.01 is stable.
```

## Run a full mission (Mode A)

```bash
cd backend
python -m app.loop.run_mission --mission-id mission_demo
#   --mission <path/to/mission.yaml>   (default: examples/tiny_cnn/mission.yaml)
#   --events-path <path>               (default: runs/<id>/events.jsonl)
# or from repo root: python backend/app/loop/run_mission.py --mission-id mission_demo
```

A run takes ~50s on CPU (8 experiments × ~5s). Events stream to
`runs/mission_demo/events.jsonl`; per-experiment workspaces (config.yaml,
metrics.jsonl, stdout/stderr) live in `runs/mission_demo/<exp_id>/`.

## Integration seam (W1 `/start` hook / lead)

```python
from app.loop.run_mission import run_mission
finished = run_mission(mission_id="mission_x", mission=None, events_path=None)
# mission: dict (mission_created payload) | path to mission.yaml | None (default yaml)
# returns the mission_finished payload {status,reason,best_experiment_id,best_metric}
```

The loop only ever appends via `kun_log(..., path=runs/<id>/events.jsonl)`. It
never imports/calls the backend api/events/state layers.

## The closed constraint loop (hero, deterministic — `constraints.py`)

1. `experiment_failed{nan_detected}` → `learn_constraint_from_nan(lr_at_failure=x)`
   emits `constraint_learned` with `bound {param:"learning_rate", op:">", value:x*0.5}`.
2. The constraint enters mission state (it is just an event in the log).
3. The planner injects active constraints into the LLM prompt **and**
   hard-rejects any proposal where `violates_bound(changes, constraint)` is True,
   retrying until it complies.
4. The next `experiment_proposed` respects the bound and its `rationale`
   references the constraint id.

`violates_bound` / `violated_constraints` / `learn_constraint_from_nan` are pure,
unit-tested functions:

```bash
python backend/app/loop/test_constraints.py     # standalone (no pytest needed)
# or: cd backend && python -m pytest app/loop/test_constraints.py -q
```

## LLM vs heuristic

- `LLMClient` (LiteLLM) is the **driver** when a key is present
  (`ANTHROPIC_API_KEY` in `backend/.env` or env; model id from `mission.yaml`).
- With **no key** (or on invalid JSON / schema failure → retry once → fall back),
  the **heuristic planner** runs the same loop end-to-end, subject to the **same
  constraint hard-reject filter**. The build/demo cannot hard-fail on a missing key.

## Files

| file | role |
|---|---|
| `schemas.py` | pydantic schemas (Proposal/Evaluation/DecisionOut) + canonical `Constraint`/`Bound` |
| `constraints.py` | `violates_bound`, `violated_constraints`, `learn_constraint_from_nan` (hero) |
| `planner.py` | LLM + heuristic proposer; selection policy; constraint hard-reject |
| `patcher.py` | `config-patch` (P0); `agent-edit` interface stub (P1) |
| `runner.py` | subprocess train.py, stream `metric_logged`, emit finished/failed |
| `evaluator.py` | verdict/summary/evidence/concerns (LLM + heuristic) |
| `decider.py` | decision ∈ {continue_branch,promote,reject,retry_debug,fork,stop} |
| `run_mission.py` | the Mode-A orchestrator + CLI (the integration seam) |
| `test_constraints.py` | unit tests for the hero loop |
