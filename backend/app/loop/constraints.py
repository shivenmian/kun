"""The closed constraint loop — deterministic, unit-testable, cannot no-op.

This is the HERO. Two pure, testable pieces:

  1. ``violates_bound(changes, constraint)`` / ``filter_proposal(...)`` — the
     hard-reject check the planner runs against every proposal.
  2. ``learn_constraint_from_nan(...)`` — the deterministic NaN -> LR-bound rule:
     NaN at learning_rate=x  =>  bound {param:"learning_rate", op:">", value:x*0.5}.

No LLM in this file. The determinism is the whole point — verify it explicitly.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .schemas import Bound, Constraint


# --- the bound check ----------------------------------------------------------

def _violates(value: float, op: str, limit: float) -> bool:
    """True if ``value`` falls in the BANNED region defined by (op, limit).

    ``op`` is the banned direction: bound {op:">", value:0.01} bans value > 0.01.
    """
    if op == ">":
        return value > limit
    if op == ">=":
        return value >= limit
    if op == "<":
        return value < limit
    if op == "<=":
        return value <= limit
    if op == "==":
        return value == limit
    raise ValueError(f"unknown bound op: {op!r}")


def violates_bound(changes: Dict[str, Any], constraint: Constraint) -> bool:
    """True if ``changes`` violates the constraint's structured ``bound``.

    A constraint with no bound (prose-only lesson) can never hard-reject.
    A change that does not touch the bounded param cannot violate it.
    """
    bound: Optional[Bound] = constraint.bound
    if bound is None:
        return False
    if bound.param not in changes:
        return False
    try:
        value = float(changes[bound.param])
    except (TypeError, ValueError):
        # Non-numeric change to a numerically-bounded param: not comparable.
        return False
    return _violates(value, bound.op, bound.value)


def violated_constraints(
    changes: Dict[str, Any], constraints: List[Constraint]
) -> List[Constraint]:
    """All active constraints that ``changes`` violates."""
    return [c for c in constraints if violates_bound(changes, c)]


def filter_proposal(
    changes: Dict[str, Any], constraints: List[Constraint]
) -> List[Constraint]:
    """Convenience alias: returns the list of violations (empty == accept)."""
    return violated_constraints(changes, constraints)


# --- the deterministic NaN -> constraint generator ----------------------------

def learn_constraint_from_nan(
    *,
    lr_at_failure: float,
    experiment_id: str,
    constraint_id: str,
    confidence: str = "high",
) -> Constraint:
    """Deterministic rule: NaN at learning_rate=x => ban learning_rate > x*0.5.

    Returns the canonical Constraint (source="learned") to emit as
    constraint_learned. This is demo-critical and must be deterministic.
    """
    value = round(lr_at_failure * 0.5, 6)
    bound = Bound(param="learning_rate", op=">", value=value)
    text = (
        f"learning_rate={lr_at_failure} caused NaNs ({experiment_id}). "
        f"Ban learning_rate > {value}."
    )
    return Constraint(
        constraint_id=constraint_id,
        source="learned",
        text=text,
        applies_to=["learning_rate"],
        bound=bound,
        confidence=confidence,
        supporting_experiments=[experiment_id],
    )


def constraints_prompt_block(constraints: List[Constraint]) -> str:
    """Human-readable list of active constraints to inject into the LLM prompt."""
    if not constraints:
        return "(none)"
    lines = []
    for c in constraints:
        if c.bound is not None:
            b = c.bound
            lines.append(
                f"- {c.constraint_id}: BANNED {b.param} {b.op} {b.value} "
                f"(source={c.source}). {c.text}"
            )
        else:
            lines.append(f"- {c.constraint_id}: {c.text} (source={c.source})")
    return "\n".join(lines)
