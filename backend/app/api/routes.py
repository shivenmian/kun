"""HTTP surface (CONTRACT §5 + §8.2). Path names are FROZEN — do not rename."""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, AsyncGenerator, Dict

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.api.loop_hook import start_loop
from app.events import (
    ForkRequest,
    MissionCreate,
    MissionStart,
    RegisterRequest,
    append_event,
    events_path,
    list_missions,
    mission_exists,
    read_events,
    register_mission,
)
from app.state import build_state

router = APIRouter()

# how often the SSE tailer polls the log file for new lines (CONTRACT §8.1 file-tail)
TAIL_POLL_SEC = 0.25


def _gen_mission_id() -> str:
    return "mission_" + uuid.uuid4().hex[:8]


def _require_mission(mission_id: str) -> None:
    if not mission_exists(mission_id):
        raise HTTPException(status_code=404, detail=f"unknown mission '{mission_id}'")


@router.get("/missions")
def get_missions() -> Dict[str, Any]:
    """List known mission ids (handy for the UI)."""
    return {"missions": list_missions()}


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
