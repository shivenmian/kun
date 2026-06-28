"""Planner — proposes the next experiment (operator + hypothesis + changes).

Two paths, ONE constraint filter:
  - LLM path (driver, default when a key is present): LiteLLM produces the
    proposal; active constraints are injected into the prompt AND every proposal
    is hard-rejected if it violates a structured bound (validation-retry).
  - Heuristic path (fallback + no-key baseline): a deterministic AIDE-style
    playbook over the knobs, subject to the SAME hard-reject filter.

Selection policy (deliberately dumb): draft seed -> greedily improve the best
valid node -> back off after a NaN failure (staying under the learned bound).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .constraints import constraints_prompt_block, violated_constraints
from .schemas import Constraint, Proposal


@dataclass
class NodeView:
    id: str
    operator: str
    status: str  # "success" | "failed"
    config: Dict[str, Any]  # full cumulative config used
    changes: Dict[str, Any]
    final_metrics: Dict[str, Any] = field(default_factory=dict)
    failure_type: Optional[str] = None
    parent_id: Optional[str] = None


@dataclass
class PlanContext:
    nodes: List[NodeView]
    constraints: List[Constraint]
    allowed_changes: List[str]
    baseline_config: Dict[str, Any]
    objective: Dict[str, Any]


@dataclass
class ProposalResult:
    proposal: Proposal
    parent_id: Optional[str]
    parent_config: Dict[str, Any]
    source: str  # "llm" | "heuristic" | "llm->heuristic"
    rejected_candidates: List[Dict[str, Any]] = field(default_factory=list)


# Ordered improve playbook: (param, value, hypothesis). Tried top-to-bottom.
IMPROVE_PLAYBOOK = [
    ("learning_rate", 0.003, "Lowering LR should stabilise training."),
    ("scheduler", "cosine", "Cosine scheduling should smooth convergence."),
    ("learning_rate", 0.02, "A higher peak LR may converge faster (probe the upper bound)."),
    ("augmentation", True, "Light augmentation should improve generalisation."),
    ("weight_decay", 0.0005, "Weight decay should regularise without raising dropout."),
    ("dropout", 0.5, "Higher dropout may regularise further."),
]


def _best_valid(nodes: List[NodeView], metric: str, direction: str) -> Optional[NodeView]:
    valid = [n for n in nodes if n.status == "success" and metric in n.final_metrics]
    if not valid:
        return None
    rev = direction == "maximize"
    return sorted(valid, key=lambda n: n.final_metrics[metric], reverse=rev)[0]


# --- heuristic ----------------------------------------------------------------

def _heuristic_propose(ctx: PlanContext) -> ProposalResult:
    metric = ctx.objective.get("metric", "val_accuracy")
    direction = ctx.objective.get("direction", "maximize")

    # 1) Draft seed if nothing has run yet.
    if not ctx.nodes:
        changes = {
            "learning_rate": ctx.baseline_config.get("learning_rate", 0.01),
            "optimizer": ctx.baseline_config.get("optimizer", "adam"),
            "dropout": ctx.baseline_config.get("dropout", 0.25),
        }
        return ProposalResult(
            proposal=Proposal(
                operator="draft",
                hypothesis="Baseline tiny CNN with Adam.",
                changes=changes,
                expected_outcome="Establish a baseline val_accuracy.",
                risk="low",
                rationale="Establish the baseline before optimising.",
            ),
            parent_id=None,
            parent_config=dict(ctx.baseline_config),
            source="heuristic",
        )

    best = _best_valid(ctx.nodes, metric, direction)
    last = ctx.nodes[-1]
    parent = best or last
    parent_config = parent.config

    rejected: List[Dict[str, Any]] = []

    # 2) Back off after a NaN failure -> stay under the learned bound. This is
    #    where the hard-reject is demonstrated: try a still-too-high LR first
    #    (rejected by the bound), then a compliant one.
    if last.status == "failed" and last.failure_type == "nan_detected":
        failed_lr = float(last.config.get("learning_rate", 0.02))
        candidates = [round(failed_lr * 0.75, 4), round(failed_lr * 0.2, 4)]
        lr_constraints = [
            c for c in ctx.constraints if c.bound and c.bound.param == "learning_rate"
        ]
        cref = lr_constraints[0] if lr_constraints else None
        for cand in candidates:
            changes = {"learning_rate": cand}
            viol = violated_constraints(changes, ctx.constraints)
            if viol:
                rejected.append(
                    {"changes": changes, "violated": [c.constraint_id for c in viol]}
                )
                continue
            if cref is not None:
                rationale = (
                    f"Respecting learned constraint {cref.constraint_id} "
                    f"(banned learning_rate > {cref.bound.value}): backed off LR to "
                    f"{cand} from the diverged {failed_lr}; expect stable training."
                )
            else:
                rationale = f"Backing off LR to {cand} after NaN at {failed_lr}."
            return ProposalResult(
                proposal=Proposal(
                    operator="improve",
                    hypothesis="Stay below the learned LR bound while keeping the schedule.",
                    changes=changes,
                    expected_outcome="Stable training, recovering accuracy.",
                    risk="low",
                    rationale=rationale,
                ),
                parent_id=best.id if best else None,
                parent_config=parent_config,
                source="heuristic",
                rejected_candidates=rejected,
            )

    # 3) Greedy improve: first playbook move that changes something, is allowed,
    #    not already applied at the parent, and respects all active constraints.
    tried = {(k, json.dumps(v)) for n in ctx.nodes for k, v in n.changes.items()}
    for param, value, hypo in IMPROVE_PLAYBOOK:
        if param not in ctx.allowed_changes:
            continue
        if parent_config.get(param) == value:
            continue
        if (param, json.dumps(value)) in tried:
            continue
        changes = {param: value}
        viol = violated_constraints(changes, ctx.constraints)
        if viol:
            rejected.append(
                {"changes": changes, "violated": [c.constraint_id for c in viol]}
            )
            continue
        return ProposalResult(
            proposal=Proposal(
                operator="improve",
                hypothesis=hypo,
                changes=changes,
                expected_outcome=f"Improve {metric} over the current best.",
                risk="medium" if param == "learning_rate" else "low",
                rationale=f"{hypo} Building on the best valid node {parent.id}.",
            ),
            parent_id=parent.id,
            parent_config=parent_config,
            source="heuristic",
            rejected_candidates=rejected,
        )

    # 4) Exhausted playbook -> signal stop via a no-op draft the loop treats as done.
    return ProposalResult(
        proposal=Proposal(
            operator="improve",
            hypothesis="No further constraint-respecting moves remain.",
            changes={},
            rationale="Search space exhausted under active constraints.",
        ),
        parent_id=parent.id,
        parent_config=parent_config,
        source="heuristic",
        rejected_candidates=rejected,
    )


# --- LLM ----------------------------------------------------------------------

_SYSTEM = (
    "You are the PLANNER in an autonomous ML research loop optimising a tiny CNN "
    "on Fashion-MNIST. Propose ONE next experiment as a config change. You MUST "
    "obey all active constraints (banned regions). Respond with ONLY a JSON object: "
    '{"operator":"draft|improve|debug","hypothesis":str,"changes":{param:value},'
    '"expected_outcome":str,"risk":str,"rationale":str}. '
    "changes keys must be among the allowed_changes."
)


def _llm_user_prompt(ctx: PlanContext, best: Optional[NodeView], note: str = "") -> str:
    history = []
    for n in ctx.nodes[-6:]:
        m = n.final_metrics.get(ctx.objective.get("metric", "val_accuracy"))
        history.append(
            f"  {n.id} [{n.operator}] {n.status} changes={n.changes} "
            f"{ctx.objective.get('metric')}={m} fail={n.failure_type}"
        )
    return (
        f"Objective: {json.dumps(ctx.objective)}\n"
        f"Allowed changes: {ctx.allowed_changes}\n"
        f"Baseline config: {json.dumps(ctx.baseline_config)}\n"
        f"Best valid node: {best.id if best else None} "
        f"config={best.config if best else None}\n"
        f"Recent history:\n" + ("\n".join(history) or "  (none)") + "\n"
        f"ACTIVE CONSTRAINTS (you MUST respect these bounds):\n"
        f"{constraints_prompt_block(ctx.constraints)}\n"
        f"{note}\n"
        "Propose the next experiment as JSON."
    )


def _validate(raw: Dict[str, Any]) -> Optional[Proposal]:
    try:
        return Proposal.model_validate(raw)
    except Exception:
        return None


def propose(ctx: PlanContext, llm=None) -> ProposalResult:
    """Top-level proposer. Uses the LLM if available, else the heuristic. The
    constraint hard-reject is applied to BOTH paths."""
    metric = ctx.objective.get("metric", "val_accuracy")
    direction = ctx.objective.get("direction", "maximize")
    best = _best_valid(ctx.nodes, metric, direction)

    if llm is not None and llm.available():
        note = ""
        for attempt in range(2):
            raw = llm.complete_json(_SYSTEM, _llm_user_prompt(ctx, best, note))
            prop = _validate(raw) if raw else None
            if prop is None:
                note = "Your previous output was invalid JSON. Return ONLY the JSON object."
                continue
            viol = violated_constraints(prop.changes, ctx.constraints)
            if viol:
                ids = ", ".join(c.constraint_id for c in viol)
                note = (
                    f"Your proposal {prop.changes} VIOLATES constraint(s) {ids}. "
                    "Propose a different change that respects all bounds."
                )
                continue
            parent = best or (ctx.nodes[-1] if ctx.nodes else None)
            return ProposalResult(
                proposal=prop,
                parent_id=parent.id if parent else None,
                parent_config=parent.config if parent else dict(ctx.baseline_config),
                source="llm",
            )
        # LLM failed twice -> heuristic fallback (still constraint-filtered).
        res = _heuristic_propose(ctx)
        res.source = "llm->heuristic"
        return res

    return _heuristic_propose(ctx)
