"""Live steering inputs for the Mode-A loop (CONTRACT §9).

The loop's steering INPUTS are exactly two, and NEITHER is the API:
  (a) steering EVENTS the loop reads back from its OWN event log
      (``instruction_added``, ``experiment_approved``, ``experiment_rejected``,
      ``fork_created`` + ``branch_created``), and
  (b) the CONTROL FILE the API writes (``runs/<id>/control.json``) — imperative
      run-state (run | pause | stop) + the approval-gate toggle.

This module holds the PURE, unit-testable readers/resolvers; ``run_mission``
wires them into the loop and owns the (impure) blocking polls. The loop still
emits ONLY via ``kun_log`` and never imports the API. The control file is a
read-only input here, so consulting it does not violate that invariant.

Default behaviour with NO control file and NO steering events is a no-op, so P0
missions run byte-for-byte unchanged.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .schemas import Bound, Constraint

# CONTRACT §9.2: file absent => run / no approval gate (P0 unchanged).
DEFAULT_CONTROL: Dict[str, Any] = {"run_state": "run", "approval_required": False}
VALID_RUN_STATES = ("run", "pause", "stop")


# --- control file (§9.2) ------------------------------------------------------

def read_control(path: Optional[str]) -> Dict[str, Any]:
    """Read ``runs/<id>/control.json`` -> ``{run_state, approval_required}``.

    Returns the default (``run`` / no approval) whenever the file is absent,
    empty, malformed, or carries an unknown ``run_state`` — so a missing or
    half-written control file can never wedge or crash the loop.
    """
    out = dict(DEFAULT_CONTROL)
    if not path or not os.path.exists(path):
        return out
    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError, ValueError):
        return out
    if not isinstance(data, dict):
        return out
    rs = data.get("run_state")
    if rs in VALID_RUN_STATES:
        out["run_state"] = rs
    out["approval_required"] = bool(data.get("approval_required", False))
    return out


# --- helpers ------------------------------------------------------------------

def exp_num(exp_id: Optional[str]) -> Optional[int]:
    """``exp_007`` -> 7. ``None``/garbage -> ``None``."""
    if not exp_id:
        return None
    digits = "".join(ch for ch in str(exp_id) if ch.isdigit())
    return int(digits) if digits else None


# --- mid-run instructions (§9.3) ---------------------------------------------

@dataclass
class InstructionView:
    instruction_id: str
    text: str
    applies_from: Optional[str] = None
    bound: Optional[Dict[str, Any]] = None


def read_instructions(events: List[Dict[str, Any]]) -> List[InstructionView]:
    """All ``instruction_added`` events, in log order."""
    out: List[InstructionView] = []
    for e in events:
        if e.get("type") != "instruction_added":
            continue
        p = e.get("payload", {}) or {}
        out.append(
            InstructionView(
                instruction_id=p.get("instruction_id")
                or e.get("event_id")
                or f"instr_{len(out) + 1:03d}",
                text=p.get("text", "") or "",
                applies_from=p.get("applies_from"),
                bound=p.get("bound"),
            )
        )
    return out


def instruction_applies(instr: InstructionView, exp_i: int) -> bool:
    """True if ``instr`` should bias the proposal for ``exp_i`` (§9.3:
    ``experiment_id >= applies_from``; absent ``applies_from`` => from now on)."""
    n = exp_num(instr.applies_from)
    return n is None or exp_i >= n


def apply_instructions(
    events: List[Dict[str, Any]],
    exp_i: int,
    active: List[Constraint],
    applied_bound_ids: set,
) -> List[str]:
    """Fold applicable instructions into the loop's state.

    - Returns the list of instruction TEXTS that apply to ``exp_i`` (soft bias
      the planner injects into its prompt).
    - For any applicable instruction carrying a structured ``bound``, appends a
      ``source="human"`` :class:`Constraint` to ``active`` (mutated in place) so
      it HARD-REJECTS like a constraint (§3). ``applied_bound_ids`` guards
      against re-adding the same instruction's bound on later iterations.
    """
    texts: List[str] = []
    for instr in read_instructions(events):
        if not instruction_applies(instr, exp_i):
            continue
        if instr.text:
            texts.append(instr.text)
        if instr.bound and instr.instruction_id not in applied_bound_ids:
            try:
                bound = Bound.model_validate(instr.bound)
            except Exception:
                applied_bound_ids.add(instr.instruction_id)  # malformed: skip once
                continue
            applied_bound_ids.add(instr.instruction_id)
            if any(c.constraint_id == instr.instruction_id for c in active):
                continue
            active.append(
                Constraint(
                    constraint_id=instr.instruction_id,
                    source="human",
                    text=instr.text or f"Human instruction {instr.instruction_id}",
                    applies_to=[bound.param],
                    bound=bound,
                )
            )
    return texts


# --- approval gate (§9.3) -----------------------------------------------------

@dataclass
class ApprovalOutcome:
    # "approved" | "approved_edited" | "rejected_replacement" | "rejected" | "stop"
    kind: str
    changes: Optional[Dict[str, Any]] = None


def resolve_approval(
    events: List[Dict[str, Any]], exp_id: str
) -> Optional[ApprovalOutcome]:
    """Resolve the approval gate for ``exp_id`` from the log, or ``None`` if no
    approve/reject for it has been emitted yet.

    - ``experiment_approved{edited:false}``        -> run as proposed.
    - ``experiment_approved{edited:true, changes}`` -> run the human's changes.
    - ``experiment_rejected{replacement_changes}``  -> run the replacement (improve).
    - ``experiment_rejected`` (no/empty replacement) -> reject the node.
    """
    for e in events:
        if e.get("experiment_id") != exp_id:
            continue
        et = e.get("type")
        p = e.get("payload", {}) or {}
        if et == "experiment_approved":
            changes = p.get("changes")
            if p.get("edited") and isinstance(changes, dict) and changes:
                return ApprovalOutcome("approved_edited", dict(changes))
            return ApprovalOutcome("approved")
        if et == "experiment_rejected":
            repl = p.get("replacement_changes")
            if isinstance(repl, dict) and repl:  # non-empty => human improve
                return ApprovalOutcome("rejected_replacement", dict(repl))
            return ApprovalOutcome("rejected")
    return None


# --- live fork execution (§9.3) ----------------------------------------------

@dataclass
class PendingFork:
    branch_id: str
    parent_experiment_id: Optional[str]
    instruction: str = ""
    constraint: Optional[Dict[str, Any]] = None


_EXP_EVENT_TYPES = (
    "experiment_proposed",
    "experiment_started",
    "experiment_finished",
    "experiment_failed",
)


def next_pending_fork(events: List[Dict[str, Any]]) -> Optional[PendingFork]:
    """The earliest ``fork_created`` branch that (a) has a matching
    ``branch_created`` and (b) has NO experiments yet — i.e. an executable fork
    the loop should run the next proposal on. ``None`` when there is none."""
    created_branches = {
        e.get("branch_id")
        for e in events
        if e.get("type") == "branch_created" and e.get("branch_id")
    }
    busy = {
        e.get("branch_id")
        for e in events
        if e.get("type") in _EXP_EVENT_TYPES and e.get("branch_id")
    }
    for e in events:
        if e.get("type") != "fork_created":
            continue
        b = e.get("branch_id")
        if not b or b == "branch_main":
            continue
        if b not in created_branches or b in busy:
            continue
        p = e.get("payload", {}) or {}
        return PendingFork(
            branch_id=b,
            parent_experiment_id=e.get("parent_experiment_id"),
            instruction=p.get("instruction", "") or "",
            constraint=p.get("constraint"),
        )
    return None
