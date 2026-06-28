"""Pydantic v2 models for the Kun event envelope + P0 event types (CONTRACT §1, §2).

Payloads are intentionally permissive (Dict[str, Any]) — the event schema is frozen
(docs/03-event-schema.md) and the materialized model is derived in state/builder.py, so
we do not re-validate every payload field here. We only pin the envelope shape.
"""
from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field

# The P0 event types the loop/cockpit produce & consume (CONTRACT §2). Kept as a
# constant for reference/validation; unknown types are tolerated by the state builder.
P0_EVENT_TYPES = {
    "mission_created",
    "mission_started",
    "branch_created",
    "constraint_added",
    "experiment_proposed",
    "file_diff_created",
    "experiment_started",
    "command_output",
    "metric_logged",
    "experiment_finished",
    "experiment_failed",
    "evaluation_created",
    "decision_created",
    "constraint_learned",
    "fork_created",
    "mission_finished",
}


class Actor(BaseModel):
    """CONTRACT §1: actor = agent or human."""

    type: Literal["agent", "human"]
    name: str
    model: Optional[str] = None


class EventEnvelope(BaseModel):
    """The full on-disk event shape (CONTRACT §1). kun_log auto-fills schema_version,
    event_id, timestamp; producers pass type, payload, and the envelope ids."""

    schema_version: int = 1
    event_id: str
    timestamp: str
    type: str
    mission_id: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    experiment_id: Optional[str] = None
    branch_id: Optional[str] = None
    parent_experiment_id: Optional[str] = None
    actor: Optional[Actor] = None


# ---- request bodies for the HTTP surface (CONTRACT §5) ----


class MissionCreate(BaseModel):
    """Body for POST /missions == the mission_created payload (CONTRACT §2). Permissive:
    the cockpit/loop may send any subset of the documented fields. mission_id optional —
    backend generates one when absent."""

    model_config = {"extra": "allow"}

    mission_id: Optional[str] = None
    name: Optional[str] = None
    goal: Optional[str] = None
    objective: Optional[Dict[str, Any]] = None
    budget: Optional[Dict[str, Any]] = None
    adapter: Optional[str] = None
    editable_files: Optional[list] = None
    allowed_changes: Optional[list] = None
    constraints: Optional[list] = None


class MissionStart(BaseModel):
    """Body for POST /missions/{id}/start -> mission_started payload (CONTRACT §2)."""

    mode: Literal["live", "replay"] = "live"
    started_by: str = "user"


class ForkRequest(BaseModel):
    """Body for POST /missions/{id}/fork (CONTRACT §5: record-only in P0).

    Emits fork_created + branch_created (+ constraint_added when `constraint` present)."""

    model_config = {"extra": "allow"}

    instruction: Optional[str] = None
    reason: Optional[str] = None
    branch_name: Optional[str] = None
    parent_experiment_id: Optional[str] = None
    constraint: Optional[Dict[str, Any]] = None  # canonical constraint object (CONTRACT §3)


class RegisterRequest(BaseModel):
    """Body for POST /missions/register (CONTRACT §8.2)."""

    mission_id: str
    events_path: Optional[str] = None


# ---- P1 steering request bodies (CONTRACT §5.1 / §9; doc 03 "Human steering events") ----


class InstructRequest(BaseModel):
    """Body for POST /missions/{id}/instruct -> instruction_added payload (CONTRACT §5.1).

    `bound`, when present, is a canonical constraint bound (CONTRACT §3) so the loop can
    hard-reject like a constraint, not just soft-bias."""

    model_config = {"extra": "allow"}

    text: str
    applies_from: Optional[str] = None
    bound: Optional[Dict[str, Any]] = None


class ApproveRequest(BaseModel):
    """Body for POST /missions/{id}/experiments/{exp_id}/approve -> experiment_approved."""

    model_config = {"extra": "allow"}

    edited: Optional[bool] = None
    changes: Optional[Dict[str, Any]] = None
    note: Optional[str] = None


class RejectRequest(BaseModel):
    """Body for POST /missions/{id}/experiments/{exp_id}/reject -> experiment_rejected."""

    model_config = {"extra": "allow"}

    reason: str
    replacement_changes: Optional[Dict[str, Any]] = None


class StopRequest(BaseModel):
    """Body for POST /missions/{id}/stop — the loop-control endpoint (CONTRACT §5.1/§9.2).

    `action` maps to control.json run_state: stop->"stop", pause->"pause", resume->"run".
    `approval_required` (when present) toggles the approval gate mid-run; when omitted the
    existing control-file value is preserved."""

    action: Literal["stop", "pause", "resume"]
    approval_required: Optional[bool] = None
    reason: Optional[str] = None
