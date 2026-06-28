"""Evaluator — judges a completed/failed experiment (verdict + evidence).

LLM path when available; deterministic heuristic fallback otherwise. Emits the
evaluation_created payload (verdict/summary/evidence/concerns).
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .schemas import Evaluation


def _heuristic_eval(
    *,
    result: Dict[str, Any],
    changes: Dict[str, Any],
    metric: str,
    direction: str,
    prev_best: Optional[float],
) -> Evaluation:
    if result["status"] == "failed":
        ft = result.get("failure_type", "error")
        if ft == "nan_detected":
            return Evaluation(
                verdict="reject",
                summary="Diverged to NaN; learning rate too high. Learned an upper bound.",
                evidence=["training loss became NaN", f"changes={changes}"],
                concerns=["instability at this learning rate"],
            )
        return Evaluation(
            verdict="reject",
            summary=f"Run failed ({ft}).",
            evidence=[result.get("message", ft)],
            concerns=[ft],
        )

    val = result.get("final_metrics", {}).get(metric)
    if val is None:
        return Evaluation(verdict="neutral", summary="No metric recorded.", evidence=[])

    if prev_best is None:
        return Evaluation(
            verdict="promote",
            summary=f"Baseline established at {val}.",
            evidence=["baseline run", f"{metric}={val}"],
        )

    improved = val > prev_best if direction == "maximize" else val < prev_best
    delta = round(val - prev_best, 4)
    if improved:
        return Evaluation(
            verdict="promote",
            summary=f"{metric} improved to {val} ({delta:+}).",
            evidence=[f"{delta:+} vs previous best {prev_best}", "stable"],
        )
    return Evaluation(
        verdict="reject",
        summary=f"{metric} did not improve ({val} vs best {prev_best}).",
        evidence=[f"{delta:+} vs best"],
        concerns=["no improvement"],
    )


_SYSTEM = (
    "You are the EVALUATOR in an autonomous ML loop. Judge the experiment result. "
    'Respond ONLY with JSON: {"verdict":"promote|reject|neutral","summary":str,'
    '"evidence":[str],"concerns":[str]}.'
)


def evaluate(
    *,
    result: Dict[str, Any],
    changes: Dict[str, Any],
    objective: Dict[str, Any],
    prev_best: Optional[float],
    llm=None,
) -> Evaluation:
    metric = objective.get("metric", "val_accuracy")
    direction = objective.get("direction", "maximize")
    if llm is not None and llm.available():
        user = (
            f"Objective: {json.dumps(objective)}\n"
            f"Proposed changes: {json.dumps(changes)}\n"
            f"Result: {json.dumps(result.get('final_metrics') or result)}\n"
            f"Status: {result['status']} failure={result.get('failure_type')}\n"
            f"Previous best {metric}: {prev_best}\n"
            "Evaluate this experiment as JSON."
        )
        raw = llm.complete_json(_SYSTEM, user)
        if raw:
            try:
                return Evaluation.model_validate(raw)
            except Exception:
                pass
    return _heuristic_eval(
        result=result, changes=changes, metric=metric, direction=direction,
        prev_best=prev_best,
    )
