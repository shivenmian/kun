"""run_mission — the Mode-A autonomous loop entry point (callable + CLI).

Drives planner -> patcher -> runner -> (constraint generator) -> evaluator ->
decider, emitting ALL events through ``kun_log`` to runs/<mission_id>/events.jsonl
in the same shape/order as examples/replays/sample.events.jsonl.

This is the seam W1's POST /missions/{id}/start hook (and the lead's integration)
invokes:

    from app.loop.run_mission import run_mission
    run_mission(mission_id="mission_x", mission=<dict|path|None>, events_path=None)

CLI:
    cd backend && python -m app.loop.run_mission --mission-id mission_x
    python backend/app/loop/run_mission.py --mission-id mission_x
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Dict, List, Optional, Union

import yaml

# --- make `kun` (repo root) and `app` importable regardless of entry point ----
_THIS = os.path.abspath(__file__)
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(_THIS), "..", "..", ".."))
BACKEND_ROOT = os.path.join(REPO_ROOT, "backend")
for p in (REPO_ROOT, BACKEND_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from kun.log import kun_log  # noqa: E402

from app.loop import constraints as C  # noqa: E402
from app.loop import evaluator as EV  # noqa: E402
from app.loop import decider as DEC  # noqa: E402
from app.loop import planner as PL  # noqa: E402
from app.loop import runner as RUN  # noqa: E402
from app.loop.llm_client import LLMClient  # noqa: E402
from app.loop.patcher import apply_config_patch  # noqa: E402
from app.loop.schemas import Constraint  # noqa: E402

BRANCH_MAIN = "branch_main"
DEFAULT_MISSION_YAML = os.path.join(REPO_ROOT, "examples", "tiny_cnn", "mission.yaml")
BASELINE_CONFIG = os.path.join(REPO_ROOT, "examples", "tiny_cnn", "config.yaml")


class Emitter:
    """Wraps kun_log with the per-mission path + mission_id baked in."""

    def __init__(self, mission_id: str, path: str):
        self.mission_id = mission_id
        self.path = path

    def __call__(self, event_type: str, payload: Dict[str, Any], **env) -> Dict[str, Any]:
        return kun_log(
            event_type, payload, mission_id=self.mission_id, path=self.path, **env
        )


def _rel(path: str) -> str:
    return os.path.relpath(path, REPO_ROOT)


def _load_mission(mission: Union[Dict[str, Any], str, None]) -> Dict[str, Any]:
    if isinstance(mission, dict):
        return mission
    path = mission or DEFAULT_MISSION_YAML
    with open(path) as f:
        return yaml.safe_load(f)


def _agent_actor(name: str, model: str) -> Dict[str, Any]:
    return {"type": "agent", "name": name, "model": model}


def run_mission(
    *,
    mission_id: str,
    mission: Union[Dict[str, Any], str, None] = None,
    events_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the full Mode-A loop. Returns the mission_finished payload."""
    spec = _load_mission(mission)
    model = spec.get("model", "claude-opus-4-8")
    objective = spec.get("objective", {"metric": "val_accuracy", "direction": "maximize"})
    metric = objective.get("metric", "val_accuracy")
    direction = objective.get("direction", "maximize")
    budget = spec.get("budget", {})
    max_experiments = int(budget.get("max_experiments", 8))
    timeout_sec = int(budget.get("max_runtime_per_experiment_sec", 90))
    target = objective.get("target")
    allowed_changes = spec.get("allowed_changes", [])

    with open(BASELINE_CONFIG) as f:
        baseline_config = yaml.safe_load(f)

    runs_dir = os.path.join(REPO_ROOT, "runs", mission_id)
    os.makedirs(runs_dir, exist_ok=True)
    events_path = events_path or os.path.join(runs_dir, "events.jsonl")
    emit = Emitter(mission_id, events_path)

    llm = LLMClient(model)
    path_kind = "LLM" if llm.available() else "heuristic"
    print(f"[run_mission] {mission_id} driver={path_kind} model={model}", flush=True)

    # --- mission_created + mission_started ---
    emit("mission_created", spec)
    emit("mission_started", {"mode": "live", "started_by": "user"},
         actor={"type": "human", "name": "user"})

    # --- seed human constraints (canonical objects) into memory ---
    active: List[Constraint] = []
    for raw in spec.get("constraints", []) or []:
        try:
            c = Constraint.model_validate(raw)
        except Exception:
            continue
        active.append(c)
        emit("constraint_added", c.to_payload(), branch_id=BRANCH_MAIN,
             actor={"type": "human", "name": "user"})

    nodes: List[PL.NodeView] = []
    learned_counter = 0
    best_value: Optional[float] = None
    best_id: Optional[str] = None
    stop_reason = "max_experiments_reached"

    exp_i = 0
    while exp_i < max_experiments:
        exp_id = f"exp_{exp_i:03d}"
        ctx = PL.PlanContext(
            nodes=nodes, constraints=active, allowed_changes=allowed_changes,
            baseline_config=baseline_config, objective=objective,
        )
        res = PL.propose(ctx, llm=llm)
        prop = res.proposal

        # Exhausted, constraint-respecting search space -> stop cleanly.
        if not prop.changes and prop.operator != "draft":
            stop_reason = "search_exhausted"
            break

        parent_id = res.parent_id
        parent_config = res.parent_config
        env = {"experiment_id": exp_id, "branch_id": BRANCH_MAIN,
               "parent_experiment_id": parent_id}

        # --- experiment_proposed ---
        prop_payload = {
            "operator": prop.operator,
            "hypothesis": prop.hypothesis,
            "changes": prop.changes,
            "expected_outcome": prop.expected_outcome,
            "risk": prop.risk,
            "rationale": prop.rationale,
        }
        emit("experiment_proposed", prop_payload, actor=_agent_actor("planner", model), **env)
        if res.rejected_candidates:
            print(f"[planner] {exp_id} hard-rejected (bound): "
                  f"{res.rejected_candidates} -> chose {prop.changes}", flush=True)

        # --- patch + file_diff_created ---
        workspace = os.path.join(runs_dir, exp_id)
        if parent_id is None:
            base_label = _rel(BASELINE_CONFIG)
        else:
            base_label = _rel(os.path.join(runs_dir, parent_id, "config.yaml"))
        new_label = _rel(os.path.join(workspace, "config.yaml"))
        config_path, diff, _ = apply_config_patch(
            base_config=parent_config, changes=prop.changes,
            workspace_dir=workspace, base_file_path=base_label, new_file_path=new_label,
        )
        emit("file_diff_created",
             {"file_path": new_label, "base_file_path": base_label, "diff": diff},
             experiment_id=exp_id, branch_id=BRANCH_MAIN)

        # --- run (emits experiment_started, metric_logged*, finished/failed) ---
        result = RUN.run_experiment(
            config_path=config_path, workspace_dir=workspace,
            timeout_sec=timeout_sec, emit=emit, envelope=env,
        )

        full_config = dict(parent_config)
        full_config.update(prop.changes)

        # --- closed constraint loop: NaN -> deterministic constraint_learned ---
        if result["status"] == "failed" and result.get("failure_type") == "nan_detected":
            lr = float(full_config.get("learning_rate", 0.0))
            learned_counter += 1
            cid = f"learned_{learned_counter:03d}"
            constraint = C.learn_constraint_from_nan(
                lr_at_failure=lr, experiment_id=exp_id, constraint_id=cid,
            )
            active.append(constraint)
            emit("constraint_learned", constraint.to_payload(),
                 experiment_id=exp_id, branch_id=BRANCH_MAIN)
            print(f"[constraint] {exp_id} NaN at lr={lr} -> {cid} "
                  f"bans learning_rate > {constraint.bound.value}", flush=True)

        # --- evaluate ---
        evaluation = EV.evaluate(
            result=result, changes=prop.changes, objective=objective,
            prev_best=best_value, llm=llm,
        )
        eval_payload = {
            "verdict": evaluation.verdict,
            "summary": evaluation.summary,
            "evidence": evaluation.evidence,
            "concerns": evaluation.concerns,
        }
        emit("evaluation_created", eval_payload,
             actor=_agent_actor("evaluator", model),
             experiment_id=exp_id, branch_id=BRANCH_MAIN)

        # --- record node + update best ---
        node = PL.NodeView(
            id=exp_id, operator=prop.operator, status=result["status"],
            config=full_config, changes=prop.changes,
            final_metrics=result.get("final_metrics", {}),
            failure_type=result.get("failure_type"), parent_id=parent_id,
        )
        nodes.append(node)
        if result["status"] == "success":
            val = result.get("final_metrics", {}).get(metric)
            if val is not None:
                better = (best_value is None or
                          (val > best_value if direction == "maximize" else val < best_value))
                if better:
                    best_value, best_id = val, exp_id

        # --- decide ---
        decision = DEC.decide(
            evaluation=evaluation, result=result, experiment_id=exp_id,
            best_valid_id=best_id,
        )
        emit("decision_created",
             {"decision": decision.decision, "rationale": decision.rationale,
              "next_action": decision.next_action.model_dump()},
             experiment_id=exp_id, branch_id=BRANCH_MAIN)

        exp_i += 1

        # --- stop on target reached ---
        if target is not None and best_value is not None:
            hit = (best_value >= target if direction == "maximize"
                   else best_value <= target)
            if hit:
                stop_reason = "target_metric_reached"
                break

    finished = {
        "status": "completed",
        "reason": stop_reason,
        "best_experiment_id": best_id,
        "best_metric": {"name": metric, "value": best_value},
    }
    emit("mission_finished", finished)
    print(f"[run_mission] done: {finished}", flush=True)
    return finished


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run a Kun Mode-A tiny-CNN mission.")
    ap.add_argument("--mission-id", required=True)
    ap.add_argument("--mission", default=None,
                    help="Path to mission.yaml (default: examples/tiny_cnn/mission.yaml)")
    ap.add_argument("--events-path", default=None)
    args = ap.parse_args(argv)
    run_mission(mission_id=args.mission_id, mission=args.mission,
                events_path=args.events_path)


if __name__ == "__main__":
    main()
