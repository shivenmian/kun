"""Decider — turns an evaluation into a selection-policy decision.

decision in {continue_branch, promote, reject, retry_debug, fork, stop}. Each
decision carries a next_action so the graph shows *why* a node was expanded.
Heuristic by default; LLM may refine (kept deterministic for the demo spine).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from .schemas import DecisionOut, Evaluation, NextAction


def decide(
    *,
    evaluation: Evaluation,
    result: Dict[str, Any],
    experiment_id: str,
    best_valid_id: Optional[str],
) -> DecisionOut:
    # Failure -> back off and continue from the best valid node.
    if result["status"] == "failed":
        if result.get("failure_type") == "nan_detected":
            return DecisionOut(
                decision="retry_debug",
                rationale="Diverged; back off below the learned bound and continue "
                "from the best valid node.",
                next_action=NextAction(parent_experiment_id=best_valid_id),
            )
        return DecisionOut(
            decision="reject",
            rationale="Run failed; abandon this node.",
            next_action=NextAction(parent_experiment_id=best_valid_id),
        )

    # This node is the current best (the baseline, or a new high-water mark the
    # evaluator may have phrased as "neutral") -> promote it. run_mission updates
    # best_valid_id BEFORE calling decide, so best_valid_id == experiment_id means
    # "this node is now the best valid node."
    if best_valid_id == experiment_id or evaluation.verdict == "promote":
        return DecisionOut(
            decision="promote",
            rationale=evaluation.summary or "New best valid node.",
            next_action=NextAction(parent_experiment_id=experiment_id),
        )

    # Ran fine but didn't beat the best. "neutral" = no regression -> keep the node
    # valid and keep exploring (don't paint it red); only a worse result rejects.
    if evaluation.verdict == "neutral":
        return DecisionOut(
            decision="continue_branch",
            rationale=evaluation.summary or "No improvement over best; continue exploring.",
            next_action=NextAction(parent_experiment_id=best_valid_id or experiment_id),
        )

    # Worse than the best -> reject this node, keep exploring from the best valid one.
    return DecisionOut(
        decision="reject",
        rationale=evaluation.summary,
        next_action=NextAction(parent_experiment_id=best_valid_id or experiment_id),
    )
