"""HTTP surface (CONTRACT §5 + §8.2). Path names are FROZEN — do not rename."""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.api.control import read_control, write_control
from app.api.loop_hook import loop_running, start_loop
from app.events import (
    ApproveRequest,
    ForkRequest,
    InstructRequest,
    MissionCreate,
    MissionStart,
    RegisterRequest,
    RejectRequest,
    StopRequest,
    append_event,
    events_path,
    list_missions,
    mission_exists,
    read_events,
    register_mission,
)
from app.events.log_io import _REGISTERED
from app.state import build_state

# actor stamped on every human-steering event (CONTRACT §1 / §5.1)
_HUMAN_ACTOR = {"type": "human", "name": "user"}

# action -> control.json run_state (CONTRACT §9.2)
_ACTION_TO_RUN_STATE = {"stop": "stop", "pause": "pause", "resume": "run"}
# control.json run_state -> §9.1 presentation run_state
_RUN_STATE_VIEW = {"run": "run", "pause": "paused", "stop": "stopped"}

router = APIRouter()

# how often the SSE tailer polls the log file for new lines (CONTRACT §8.1 file-tail)
TAIL_POLL_SEC = 0.25


def _gen_mission_id() -> str:
    return "mission_" + uuid.uuid4().hex[:8]


def _require_mission(mission_id: str) -> None:
    if not mission_exists(mission_id):
        raise HTTPException(status_code=404, detail=f"unknown mission '{mission_id}'")


def _mission_summary(mission_id: str) -> Dict[str, Any]:
    """One §5.2 summary row for a mission, derived purely from its event log
    (build_state) + control file. Robust: a missing/empty/corrupt log degrades to a
    minimal row instead of raising, so one bad mission never 500s the whole list."""
    try:
        events = read_events(mission_id)
    except Exception:
        events = []
    registered = mission_id in _REGISTERED

    try:
        state = build_state(events)
    except Exception:
        state = {}

    mission = state.get("mission") or {}
    # mode: from mission_started; a registered-external mission is "observe" regardless.
    mode = "observe" if registered else mission.get("mode")

    try:
        control = read_control(mission_id)
    except Exception:
        control = {}

    last_ts = events[-1].get("timestamp") if events else None

    # §5.2 attention flags — reuse the SAME derivation as GET /state (§9.1/§9.2) so the
    # two endpoints always agree. approval_required is the control-file gate; pending_approval
    # is the §9.1 object coerced to a bool for the summary row (a proposed-but-unresolved
    # experiment at the gate => the navigator badges "needs attention").
    approval_required = bool(control.get("approval_required", False))
    pending_approval = bool(_compute_pending_approval(events, state, approval_required))

    return {
        "mission_id": mission_id,
        "name": mission.get("name"),
        "run_state": _derive_run_state(events, control),
        "mode": mode,
        "experiments_count": len(state.get("experiments", [])),
        "best": _compute_best(state) if state else None,
        "updated_at": last_ts,
        "approval_required": approval_required,
        "pending_approval": pending_approval,
    }


@router.get("/missions")
def get_missions() -> Dict[str, Any]:
    """Mission-history panel (CONTRACT §5.2): one summary object per known mission,
    sorted most-recently-updated first. `missions` stays a list; each item is now an
    object (was a bare id string). Pure read over each mission's event log + control
    file — no new events. One bad/empty log degrades gracefully (see _mission_summary)."""
    summaries = [_mission_summary(mid) for mid in list_missions()]
    # most-recently-updated first; missions with no timestamp sort last (stable).
    summaries.sort(key=lambda s: s.get("updated_at") or "", reverse=True)
    return {"missions": summaries}


@router.post("/missions")
def create_mission(body: MissionCreate) -> Dict[str, Any]:
    """Create a mission: make runs/<id>/, emit mission_created. Returns {mission_id}."""
    payload = body.model_dump(exclude_none=True)
    mission_id = payload.pop("mission_id", None) or _gen_mission_id()
    append_event("mission_created", payload, mission_id=mission_id)
    return {"mission_id": mission_id}


@router.post("/missions/{mission_id}/start")
def start_mission(mission_id: str, body: MissionStart) -> Dict[str, Any]:
    """Emit mission_started, then best-effort launch the loop (W3 seam)."""
    _require_mission(mission_id)
    append_event(
        "mission_started",
        {"mode": body.mode, "started_by": body.started_by},
        mission_id=mission_id,
    )
    loop_status = start_loop(mission_id, body.mode)
    return {"mission_id": mission_id, "mode": body.mode, **loop_status}


@router.get("/missions/{mission_id}/events")
def get_events(mission_id: str) -> list:
    """Full event log as a JSON array (replay + reload)."""
    _require_mission(mission_id)
    return read_events(mission_id)


@router.get("/missions/{mission_id}/experiments")
def get_experiments(mission_id: str) -> Dict[str, Any]:
    """Materialized state (build_state) for initial hydrate."""
    _require_mission(mission_id)
    return build_state(read_events(mission_id))


@router.post("/missions/{mission_id}/fork")
def fork_mission(mission_id: str, body: ForkRequest) -> Dict[str, Any]:
    """Record-only fork (P0): fork_created + branch_created (+ constraint_added)."""
    _require_mission(mission_id)
    branch_id = "branch_" + uuid.uuid4().hex[:8]
    parent = body.parent_experiment_id

    fork_payload = {
        "instruction": body.instruction,
        "reason": body.reason,
    }
    append_event(
        "fork_created",
        {k: v for k, v in fork_payload.items() if v is not None},
        mission_id=mission_id,
        branch_id=branch_id,
        parent_experiment_id=parent,
        actor={"type": "human", "name": "user"},
    )

    branch_payload = {
        "name": body.branch_name or "fork",
        "source": "human_fork",
        "reason": body.reason,
    }
    append_event(
        "branch_created",
        {k: v for k, v in branch_payload.items() if v is not None},
        mission_id=mission_id,
        branch_id=branch_id,
        parent_experiment_id=parent,
    )

    if body.constraint:
        c = dict(body.constraint)
        c.setdefault("source", "human")
        append_event(
            "constraint_added",
            c,
            mission_id=mission_id,
            branch_id=branch_id,
        )

    return {"mission_id": mission_id, "branch_id": branch_id}


# ---------------------------------------------------------------------------
# P1 steering endpoints (CONTRACT §5.1 / §9). All additive; no P0 path renamed.
# Steering events are appended via append_event (kun_log) exactly like P0.
# ---------------------------------------------------------------------------


def _gen_instruction_id() -> str:
    return "instr_" + uuid.uuid4().hex[:8]


@router.post("/missions/{mission_id}/instruct")
def instruct_mission(mission_id: str, body: InstructRequest) -> Dict[str, Any]:
    """Emit instruction_added (human actor). A structured `bound` lets the loop hard-reject
    like a constraint; otherwise it soft-biases the next proposal (CONTRACT §9.3)."""
    _require_mission(mission_id)
    instruction_id = _gen_instruction_id()
    payload: Dict[str, Any] = {"instruction_id": instruction_id, "text": body.text}
    if body.applies_from is not None:
        payload["applies_from"] = body.applies_from
    if body.bound is not None:
        payload["bound"] = body.bound
    append_event(
        "instruction_added",
        payload,
        mission_id=mission_id,
        actor=_HUMAN_ACTOR,
    )
    return {"instruction_id": instruction_id}


@router.post("/missions/{mission_id}/experiments/{exp_id}/approve")
def approve_experiment(mission_id: str, exp_id: str, body: ApproveRequest) -> Dict[str, Any]:
    """Emit experiment_approved (human actor) for exp_id (CONTRACT §9.3 approval gate)."""
    _require_mission(mission_id)
    payload = body.model_dump(exclude_none=True)
    append_event(
        "experiment_approved",
        payload,
        mission_id=mission_id,
        experiment_id=exp_id,
        actor=_HUMAN_ACTOR,
    )
    return {"ok": True}


@router.post("/missions/{mission_id}/experiments/{exp_id}/reject")
def reject_experiment(mission_id: str, exp_id: str, body: RejectRequest) -> Dict[str, Any]:
    """Emit experiment_rejected (human actor) for exp_id. `replacement_changes`, when given,
    is run by the loop as a human `improve`; otherwise the node is rejected (CONTRACT §9.3)."""
    _require_mission(mission_id)
    payload = body.model_dump(exclude_none=True)
    append_event(
        "experiment_rejected",
        payload,
        mission_id=mission_id,
        experiment_id=exp_id,
        actor=_HUMAN_ACTOR,
    )
    return {"ok": True}


@router.post("/missions/{mission_id}/stop")
def stop_mission(mission_id: str, body: StopRequest) -> Dict[str, Any]:
    """Loop-control endpoint (CONTRACT §9.2): atomically write runs/<id>/control.json.

    action -> run_state: stop->"stop", pause->"pause", resume->"run". `approval_required`
    is set when provided, else the existing control-file value is preserved. On `stop`, if
    no loop is running the API emits mission_finished{reason:"user_stop"} directly so a stop
    always terminates (CONTRACT §5.1)."""
    _require_mission(mission_id)
    run_state = _ACTION_TO_RUN_STATE[body.action]

    current = read_control(mission_id)
    approval_required = (
        body.approval_required
        if body.approval_required is not None
        else current.get("approval_required", False)
    )
    write_control(mission_id, run_state, approval_required)

    if body.action == "stop" and not loop_running(mission_id):
        events = read_events(mission_id)
        already_finished = any(e.get("type") == "mission_finished" for e in events)
        if not already_finished:
            best = _compute_best(build_state(events))
            payload: Dict[str, Any] = {"status": "stopped", "reason": "user_stop"}
            if best is not None:
                payload["best_experiment_id"] = best.get("experiment_id")
                payload["best_metric"] = best.get("metric")
            append_event(
                "mission_finished",
                payload,
                mission_id=mission_id,
                actor=_HUMAN_ACTOR,
            )

    return {"action": body.action, "run_state": run_state}


@router.get("/missions/{mission_id}/state")
def get_state(mission_id: str) -> Dict[str, Any]:
    """Feedback / hydrate object (CONTRACT §9.1). Pure read over the event log
    (build_state) + the control file."""
    _require_mission(mission_id)
    events = read_events(mission_id)
    state = build_state(events)
    control = read_control(mission_id)
    return _build_steering_state(mission_id, events, state, control)


@router.post("/missions/register")
def register(body: RegisterRequest) -> Dict[str, Any]:
    """Register an externally-produced mission (CONTRACT §8.2) so state hydrates from its
    log and /stream tails it. Returns the resolved {mission_id, events_path}."""
    resolved = register_mission(body.mission_id, body.events_path)
    return {"mission_id": body.mission_id, "events_path": str(resolved)}


@router.get("/missions/{mission_id}/stream")
async def stream_mission(mission_id: str) -> EventSourceResponse:
    """SSE: replay all existing events, then file-tail runs/<id>/events.jsonl and push
    each newly-appended line as it arrives (CONTRACT §8.1). THE live mechanism for both
    Mode A and Mode B."""
    _require_mission(mission_id)
    path = events_path(mission_id)

    async def event_source() -> AsyncGenerator[Dict[str, Any], None]:
        sent = 0
        # 1) replay everything currently on disk
        for ev in read_events(mission_id):
            sent += 1
            yield {"event": "kun", "data": json.dumps(ev)}
        # signal end of the historical backfill so clients can mark "live"
        yield {"event": "ready", "data": json.dumps({"replayed": sent})}

        # 2) tail for new lines (poll ~250ms). Count by parsed lines so a partial
        #    trailing write is re-read on the next poll once complete.
        while True:
            await asyncio.sleep(TAIL_POLL_SEC)
            if not path.exists():
                continue
            current = read_events(mission_id)
            if len(current) > sent:
                for ev in current[sent:]:
                    yield {"event": "kun", "data": json.dumps(ev)}
                sent = len(current)

    return EventSourceResponse(event_source())


# ---------------------------------------------------------------------------
# GET /state derivation helpers (CONTRACT §9.1). Pure functions over the event
# log + build_state output + the control file. No loop import; tolerant of
# unknown/partial events.
# ---------------------------------------------------------------------------


def _derive_run_state(events: List[Dict[str, Any]], control: Dict[str, Any]) -> str:
    """§9.1 presentation run_state: control.json view ("run"->run, "pause"->paused,
    "stop"->stopped), but a mission_finished event always wins -> "finished". Shared by
    GET /state and the GET /missions summaries so both derive run_state identically."""
    if any(e.get("type") == "mission_finished" for e in events):
        return "finished"
    return _RUN_STATE_VIEW.get(control.get("run_state", "run"), "run")


def _compute_pending_approval(
    events: List[Dict[str, Any]],
    state: Dict[str, Any],
    approval_required: bool,
) -> Optional[Dict[str, Any]]:
    """§9.1 pending_approval: an experiment still merely "proposed" (per build_state — it has
    NOT started/finished, so it sits at the gate) AND with no later experiment_approved/
    experiment_rejected for its id ("emitted-but-not-yet-consumed"), and only when the gate is
    on. An experiment that already ran is past the gate. Returns the {experiment_id, changes,
    operator} object (last unresolved wins) or None. Shared by GET /state (object) and the
    GET /missions summaries (coerced to bool) so both endpoints agree."""
    if not approval_required:
        return None
    resolved_ids = {
        ev.get("experiment_id")
        for ev in events
        if ev.get("type") in ("experiment_approved", "experiment_rejected")
        and ev.get("experiment_id")
    }
    pending: Optional[Dict[str, Any]] = None
    for exp in state.get("experiments", []):  # insertion order; last unresolved wins
        if exp.get("status") == "proposed" and exp.get("id") not in resolved_ids:
            pending = {
                "experiment_id": exp["id"],
                "changes": exp.get("changes"),
                "operator": exp.get("operator"),
            }
    return pending


def _compute_best(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Best experiment as {experiment_id, metric{name,value}}.

    Prefer the explicit winner recorded on mission_finished (build_state.bestExperiment);
    otherwise pick the best finished experiment by the mission objective (metric+direction).
    """
    be = state.get("bestExperiment")
    if be and be.get("id"):
        return {"experiment_id": be["id"], "metric": be.get("metric")}

    objective = (state.get("mission") or {}).get("objective") or {}
    metric_name = objective.get("metric")
    direction = (objective.get("direction") or "maximize").lower()
    if not metric_name:
        return None

    # statuses that represent a successfully-completed run (a node forked/promoted off a
    # good result still counts; buggy/rejected/proposed/running do not).
    _SUCCESS = {"valid", "promoted", "forked"}
    best_id: Optional[str] = None
    best_val: Optional[float] = None
    for exp in state.get("experiments", []):
        if exp.get("status") not in _SUCCESS:
            continue
        fm = exp.get("finalMetrics") or {}
        if metric_name not in fm:
            continue
        try:
            val = float(fm[metric_name])
        except (TypeError, ValueError):
            continue
        if best_val is None or (
            val > best_val if direction.startswith("max") else val < best_val
        ):
            best_val, best_id = val, exp["id"]

    if best_id is None:
        return None
    return {"experiment_id": best_id, "metric": {"name": metric_name, "value": best_val}}


def _build_steering_state(
    mission_id: str,
    events: List[Dict[str, Any]],
    state: Dict[str, Any],
    control: Dict[str, Any],
) -> Dict[str, Any]:
    """Assemble the §9.1 feedback object."""
    approval_required = bool(control.get("approval_required", False))

    run_state = _derive_run_state(events, control)

    # Two constraint tiers (CONTRACT §3): WITH a bound = hard/active; WITHOUT = soft lesson.
    active_constraints: List[Dict[str, Any]] = []
    soft_lessons: List[Dict[str, Any]] = []
    for c in state.get("constraints", []):
        (active_constraints if c.get("bound") else soft_lessons).append(c)

    # pending_approval: see _compute_pending_approval (shared with the GET /missions summary).
    pending_approval = _compute_pending_approval(events, state, approval_required)

    # pending_instructions: instruction_added events not yet "consumed". Best-effort
    # (documented): an instruction is consumed once a later experiment_proposed appears
    # in the log; so pending = instructions emitted after the last proposal. (applies_from
    # is surfaced for the loop but the positional heuristic drives pending-ness.)
    last_proposed_idx = -1
    for i, ev in enumerate(events):
        if ev.get("type") == "experiment_proposed":
            last_proposed_idx = i
    pending_instructions: List[Dict[str, Any]] = []
    for i, ev in enumerate(events):
        if ev.get("type") != "instruction_added" or i <= last_proposed_idx:
            continue
        p = ev.get("payload") or {}
        pending_instructions.append(
            {
                "instruction_id": p.get("instruction_id"),
                "text": p.get("text"),
                "applies_from": p.get("applies_from"),
                "bound": p.get("bound"),
            }
        )

    # pending_forks: fork-created branches with no experiments yet on that branch_id.
    branches_with_exps = {
        exp.get("branchId") for exp in state.get("experiments", []) if exp.get("branchId")
    }
    # branch_id -> a constraint_added recorded on that branch (forked constraint, if any)
    branch_constraint: Dict[str, Dict[str, Any]] = {}
    for ev in events:
        if ev.get("type") == "constraint_added" and ev.get("branch_id"):
            branch_constraint[ev["branch_id"]] = ev.get("payload") or {}
    pending_forks: List[Dict[str, Any]] = []
    seen_branches: set = set()
    for ev in events:
        if ev.get("type") != "fork_created":
            continue
        bid = ev.get("branch_id")
        if not bid or bid in seen_branches or bid in branches_with_exps:
            continue
        seen_branches.add(bid)
        p = ev.get("payload") or {}
        pending_forks.append(
            {
                "branch_id": bid,
                "parent_experiment_id": ev.get("parent_experiment_id"),
                "instruction": p.get("instruction"),
                "constraint": branch_constraint.get(bid),
            }
        )

    return {
        "mission_id": mission_id,
        "run_state": run_state,
        "approval_required": approval_required,
        "active_constraints": active_constraints,
        "soft_lessons": soft_lessons,
        "pending_approval": pending_approval,
        "pending_instructions": pending_instructions,
        "pending_forks": pending_forks,
        "best": _compute_best(state),
    }
