"""Control file I/O — imperative loop state at runs/<id>/control.json (CONTRACT §9.2).

This is the ONE channel for stop / pause / resume + the approval-gate toggle. It is NOT
an event: the API *writes* it (atomically: temp file + os.replace); the loop *reads* it at
safe points. Because it is loop input it does not violate "emit only via kun_log".

Shape (frozen, CONTRACT §9.2):
    {"run_state": "run | pause | stop", "approval_required": false, "updated_at": "<iso>"}

Default when the file is absent = {"run_state": "run", "approval_required": false} so P0
missions (which never write a control file) are completely unchanged.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict

from app.events import events_path

# run_state values the control file may hold (CONTRACT §9.2). Distinct from the §9.1
# /state vocabulary ("run|paused|stopped|finished") which is a presentation mapping.
CONTROL_RUN_STATES = {"run", "pause", "stop"}

DEFAULT_CONTROL: Dict[str, Any] = {"run_state": "run", "approval_required": False}


def control_path(mission_id: str) -> Path:
    """runs/<id>/control.json — sits next to the mission's events.jsonl (honors register
    overrides via events_path's parent dir)."""
    return events_path(mission_id).parent / "control.json"


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def read_control(mission_id: str) -> Dict[str, Any]:
    """Read control.json, falling back to the default (run, no approval gate). Tolerant
    of a missing / half-written file (returns the default rather than crashing)."""
    path = control_path(mission_id)
    if not path.exists():
        return dict(DEFAULT_CONTROL)
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_CONTROL)
    if not isinstance(data, dict):
        return dict(DEFAULT_CONTROL)
    out = dict(DEFAULT_CONTROL)
    if data.get("run_state") in CONTROL_RUN_STATES:
        out["run_state"] = data["run_state"]
    if isinstance(data.get("approval_required"), bool):
        out["approval_required"] = data["approval_required"]
    if "updated_at" in data:
        out["updated_at"] = data["updated_at"]
    return out


def write_control(mission_id: str, run_state: str, approval_required: bool) -> Dict[str, Any]:
    """Atomically write control.json (temp file in the same dir + os.replace so the loop
    never reads a partially-written file). Returns the written object."""
    if run_state not in CONTROL_RUN_STATES:
        raise ValueError(f"invalid run_state '{run_state}'")
    path = control_path(mission_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    obj = {
        "run_state": run_state,
        "approval_required": bool(approval_required),
        "updated_at": _now_iso(),
    }
    # temp file MUST live on the same filesystem (same dir) for os.replace to be atomic.
    tmp = path.parent / f".control.{uuid.uuid4().hex}.tmp"
    try:
        tmp.write_text(json.dumps(obj))
        os.replace(tmp, path)  # atomic on POSIX
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    return obj
