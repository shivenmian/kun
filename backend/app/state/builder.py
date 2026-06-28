"""Pure state derivation: build_state(events) -> materialized model (CONTRACT §4).

Replays the event log into the model the cockpit hydrates from. Rules:
  - Unknown event types are IGNORED, never crash (P1 events like instruction_added will
    appear later) — CONTRACT §2 tolerance requirement.
  - Status mapping (CONTRACT §4): proposed/running/valid/buggy/rejected/promoted/forked.

Status note (reconciliation): CONTRACT §4 lists decision_created{promote} -> "promoted",
but the reference trajectory marks every advancing success with decision "promote" and the
acceptance check requires the winner (exp_007) to read "valid". So a "promote" decision
does NOT downgrade/override a clean success: successful experiments stay "valid"; "promoted"
is reserved for an explicit promotion of a not-yet-valid node (does not occur in P0 sample).
A "reject" decision DOES set "rejected". This keeps valid/buggy/rejected visually distinct.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# status precedence — higher number wins so out-of-order / late events can't downgrade a
# terminal state (e.g. a trailing command_output after experiment_finished).
_STATUS_RANK = {
    "proposed": 0,
    "running": 1,
    "valid": 2,
    "promoted": 3,
    "rejected": 3,
    "buggy": 3,
    "forked": 3,
}


def _new_experiment(exp_id: str) -> Dict[str, Any]:
    return {
        "id": exp_id,
        "parentId": None,
        "branchId": "branch_main",
        "operator": None,
        "status": "proposed",
        "hypothesis": None,
        "rationale": None,
        "changes": None,
        "diff": None,
        "command": None,
        "metrics": [],
        "finalMetrics": None,
        "verdict": None,
        "evidence": None,
        "concerns": None,
    }


def _set_status(exp: Dict[str, Any], status: str) -> None:
    """Advance status only when the new state ranks >= the current one."""
    if _STATUS_RANK.get(status, -1) >= _STATUS_RANK.get(exp["status"], -1):
        exp["status"] = status


def build_state(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    mission: Dict[str, Any] = {
        "id": None,
        "name": None,
        "goal": None,
        "objective": None,
        "budget": None,
        "adapter": None,
        "editableFiles": None,
        "allowedChanges": None,
        "status": "created",
        "mode": None,
        "startedBy": None,
        "finishReason": None,
    }
    experiments: "Dict[str, Dict[str, Any]]" = {}  # insertion-ordered (py3.7+)
    branches: "Dict[str, Dict[str, Any]]" = {
        "branch_main": {"id": "branch_main", "name": "main", "source": "root",
                        "reason": None, "parentExperimentId": None}
    }
    constraints: "Dict[str, Dict[str, Any]]" = {}  # by constraint_id
    best_experiment: Optional[Dict[str, Any]] = None
    current_experiment: Optional[str] = None
    last_running: Optional[str] = None

    def exp_for(ev: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        exp_id = ev.get("experiment_id")
        if not exp_id:
            return None
        if exp_id not in experiments:
            exp = _new_experiment(exp_id)
            if ev.get("branch_id"):
                exp["branchId"] = ev["branch_id"]
            if ev.get("parent_experiment_id"):
                exp["parentId"] = ev["parent_experiment_id"]
            experiments[exp_id] = exp
        else:
            exp = experiments[exp_id]
            if ev.get("branch_id"):
                exp["branchId"] = ev["branch_id"]
            if ev.get("parent_experiment_id") and not exp["parentId"]:
                exp["parentId"] = ev["parent_experiment_id"]
        return exp

    for ev in events:
        etype = ev.get("type")
        p = ev.get("payload") or {}

        if etype == "mission_created":
            mission["id"] = ev.get("mission_id")
            mission["name"] = p.get("name")
            mission["goal"] = p.get("goal")
            mission["objective"] = p.get("objective")
            mission["budget"] = p.get("budget")
            mission["adapter"] = p.get("adapter")
            mission["editableFiles"] = p.get("editable_files")
            mission["allowedChanges"] = p.get("allowed_changes")
            # constraints[] seeded at mission creation (canonical objects)
            for c in (p.get("constraints") or []):
                cid = c.get("constraint_id")
                if cid:
                    constraints[cid] = c

        elif etype == "mission_started":
            mission["status"] = "running"
            mission["mode"] = p.get("mode")
            mission["startedBy"] = p.get("started_by")

        elif etype == "mission_finished":
            mission["status"] = p.get("status", "finished")
            mission["finishReason"] = p.get("reason")
            best_id = p.get("best_experiment_id")
            if best_id:
                best_experiment = {
                    "id": best_id,
                    "metric": p.get("best_metric"),
                }

        elif etype == "branch_created":
            bid = ev.get("branch_id")
            if bid:
                branches[bid] = {
                    "id": bid,
                    "name": p.get("name"),
                    "source": p.get("source"),
                    "reason": p.get("reason"),
                    "parentExperimentId": ev.get("parent_experiment_id"),
                }

        elif etype == "fork_created":
            # record-only in P0; mark the parent node as a fork point (CONTRACT §4 forked)
            parent_id = ev.get("parent_experiment_id")
            if parent_id and parent_id in experiments:
                _set_status(experiments[parent_id], "forked")

        elif etype in ("constraint_added", "constraint_learned"):
            cid = p.get("constraint_id")
            if cid:
                constraints[cid] = p

        elif etype == "experiment_proposed":
            exp = exp_for(ev)
            if exp is not None:
                exp["operator"] = p.get("operator")
                exp["hypothesis"] = p.get("hypothesis")
                exp["rationale"] = p.get("rationale")
                exp["changes"] = p.get("changes")
                _set_status(exp, "proposed")

        elif etype == "file_diff_created":
            exp = exp_for(ev)
            if exp is not None:
                exp["diff"] = p.get("diff")

        elif etype == "experiment_started":
            exp = exp_for(ev)
            if exp is not None:
                exp["command"] = p.get("command")
                _set_status(exp, "running")
                last_running = exp["id"]

        elif etype == "metric_logged":
            exp = exp_for(ev)
            if exp is not None:
                point = {"name": p.get("name"), "value": p.get("value"),
                         "step": p.get("step")}
                if "epoch" in p:
                    point["epoch"] = p.get("epoch")
                if "phase" in p:
                    point["phase"] = p.get("phase")
                exp["metrics"].append(point)

        elif etype == "experiment_finished":
            exp = exp_for(ev)
            if exp is not None:
                exp["finalMetrics"] = p.get("final_metrics")
                _set_status(exp, "valid")

        elif etype == "experiment_failed":
            exp = exp_for(ev)
            if exp is not None:
                exp["finalMetrics"] = p.get("last_metrics")
                exp["concerns"] = [p.get("message")] if p.get("message") else exp["concerns"]
                _set_status(exp, "buggy")

        elif etype == "evaluation_created":
            exp = exp_for(ev)
            if exp is not None:
                exp["verdict"] = p.get("verdict")
                exp["evidence"] = p.get("evidence")
                if p.get("concerns"):
                    exp["concerns"] = p.get("concerns")

        elif etype == "decision_created":
            exp = exp_for(ev)
            if exp is not None:
                decision = p.get("decision")
                if decision == "reject":
                    _set_status(exp, "rejected")
                # "promote" intentionally does NOT override "valid" (see module docstring).

        # any other (unknown / P1) event type: ignore, never crash.

    exp_list = list(experiments.values())

    # current experiment: prefer a still-running node, else the last seen.
    for exp in reversed(exp_list):
        if exp["status"] == "running":
            current_experiment = exp["id"]
            break
    if current_experiment is None:
        current_experiment = last_running or (exp_list[-1]["id"] if exp_list else None)

    # budget usage
    budget = mission.get("budget") or {}
    budget_usage = {
        "experimentsRun": len(exp_list),
        "maxExperiments": budget.get("max_experiments"),
    }

    return {
        "mission": mission,
        "experiments": exp_list,
        "branches": list(branches.values()),
        "constraints": list(constraints.values()),
        "bestExperiment": best_experiment,
        # Alias for vocabulary parity with the web reducer (keys off
        # bestExperimentId); additive — bestExperiment kept for back-compat.
        "bestExperimentId": (best_experiment or {}).get("id"),
        "currentExperiment": current_experiment,
        "mode": mission.get("mode"),
        "budgetUsage": budget_usage,
    }
