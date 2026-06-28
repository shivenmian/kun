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


# --- the deterministic underfitting -> dropout/reg bound generator ------------
#
# Mirrors the sample replay's hand-authored ``learned_002`` ("dropout > 0.4
# underfits"), which the live loop previously could not produce. Pure + rule-
# derived: a regularization knob went UP vs the parent AND both train and val
# accuracy dropped (the underfitting signature) => ban that knob above x*0.8.

# Knobs whose INCREASE adds regularization (and so can cause underfitting).
REGULARIZERS = ("dropout", "weight_decay")


def detect_underfit_param(
    *,
    changes: Dict[str, Any],
    parent_config: Dict[str, Any],
    parent_metrics: Dict[str, Any],
    child_metrics: Dict[str, Any],
    metric: str = "val_accuracy",
    train_metric: str = "train_accuracy",
) -> Optional[tuple]:
    """Return ``(param, new_value)`` if a regularization knob underfit, else None.

    Underfitting signature (all must hold for the same knob):
      * the knob is a regularizer (``REGULARIZERS``) present in ``changes``,
      * its value INCREASED vs the parent config (more regularization),
      * BOTH train accuracy and val accuracy dropped vs the parent.

    PURE — no LLM, no side effects. Returns the first matching knob.
    """
    for param in REGULARIZERS:
        if param not in changes:
            continue
        try:
            new_f = float(changes[param])
            old_f = float(parent_config.get(param))
        except (TypeError, ValueError):
            continue
        if not (new_f > old_f):  # regularization must have gone UP
            continue
        train_new = child_metrics.get(train_metric)
        train_old = parent_metrics.get(train_metric)
        val_new = child_metrics.get(metric)
        val_old = parent_metrics.get(metric)
        if None in (train_new, train_old, val_new, val_old):
            continue
        # Underfitting: capacity-starved -> BOTH train and val regress together.
        if train_new < train_old and val_new < val_old:
            return param, new_f
    return None


def learn_constraint_from_underfit(
    *,
    param: str,
    value_at_underfit: float,
    experiment_id: str,
    constraint_id: str,
    confidence: Optional[str] = None,
) -> Constraint:
    """Deterministic rule: regularizer=x underfit => ban ``param`` > x*0.8.

    For dropout=0.5 this yields ``dropout > 0.4`` — exactly the sample's
    hand-authored ``learned_002``. Returns the canonical Constraint to emit as
    ``constraint_learned`` (hard tier — it carries a ``bound``).
    """
    value = round(value_at_underfit * 0.8, 6)
    bound = Bound(param=param, op=">", value=value)
    text = (
        f"{param}={value_at_underfit} underfit the tiny CNN ({experiment_id}; "
        f"train and val accuracy both dropped). Ban {param} > {value}."
    )
    return Constraint(
        constraint_id=constraint_id,
        source="learned",
        text=text,
        applies_to=[param],
        bound=bound,
        confidence=confidence or confidence_for(1),
        supporting_experiments=[experiment_id],
    )


# --- memory hygiene: merge + confidence growth --------------------------------

def confidence_for(n_supporting: int) -> str:
    """Confidence as evidence accumulates: 1 exp = medium, >=2 = high."""
    if n_supporting >= 2:
        return "high"
    if n_supporting == 1:
        return "medium"
    return "low"


def _tighter(op: str, a: float, b: float) -> float:
    """The more restrictive of two same-op bound values (bans the wider region)."""
    if op in (">", ">="):
        return min(a, b)  # lower ban threshold rejects more
    if op in ("<", "<="):
        return max(a, b)
    return a  # "==" — nothing to tighten


def merge_learned_constraint(
    active: List[Constraint], new: Constraint
) -> tuple:
    """Merge ``new`` into ``active`` if an existing LEARNED constraint already
    bounds the same param with the same op; otherwise append.

    Returns ``(constraint_to_emit, was_merged)``. On merge the existing
    ``constraint_id`` is REUSED (so the state builder, keyed by id, keeps ONE
    entry — re-emitting it records the sharpening), the bound is tightened, the
    supporting experiments are unioned, and confidence grows with the evidence
    (1 exp = medium, >=2 = high). ``new`` MUST be a hard constraint (has a bound).
    """
    assert new.bound is not None, "merge_learned_constraint is for hard constraints"
    nb = new.bound
    for i, c in enumerate(active):
        if (
            c.source == "learned"
            and c.bound is not None
            and c.bound.param == nb.param
            and c.bound.op == nb.op
        ):
            value = _tighter(c.bound.op, c.bound.value, nb.value)
            supporting = list(
                dict.fromkeys(c.supporting_experiments + new.supporting_experiments)
            )
            n = len(supporting)
            merged = Constraint(
                constraint_id=c.constraint_id,  # stable id => one sharpened entry
                source="learned",
                text=(
                    f"{nb.param} {nb.op} {value} is banned (learned across "
                    f"{n} experiment{'s' if n != 1 else ''}: {', '.join(supporting)})."
                ),
                applies_to=c.applies_to or new.applies_to,
                bound=Bound(param=nb.param, op=nb.op, value=value),
                confidence=confidence_for(n),
                supporting_experiments=supporting,
            )
            active[i] = merged
            return merged, True
    active.append(new)
    return new, False


# --- positive Σ-summary soft lessons (SOFT tier — NO bound, bias-only) --------

def _describe_change(changes: Dict[str, Any]) -> str:
    """Compact label for a change set: 'cosine' for {scheduler: cosine},
    'learning_rate=0.003' for numeric knobs."""
    parts = []
    for k, v in changes.items():
        if isinstance(v, str):
            parts.append(str(v))
        else:
            parts.append(f"{k}={v}")
    return ", ".join(parts) or "change"


def soft_lesson_from_promotion(
    *,
    changes: Dict[str, Any],
    metric: str,
    delta: float,
    experiment_id: str,
    constraint_id: str,
) -> Constraint:
    """A SOFT lesson recorded on a promote with a positive metric delta.

    e.g. {"scheduler":"cosine"} +0.012 -> text "cosine: +0.012 val_accuracy".
    NO ``bound`` => it can never hard-reject; it only biases the planner prompt
    so a later proposal can build on a prior win (CONTRACT §3, two-tier memory).
    """
    sign = "+" if delta >= 0 else ""
    text = f"{_describe_change(changes)}: {sign}{round(delta, 4)} {metric}"
    return Constraint(
        constraint_id=constraint_id,
        source="learned",
        text=text,
        applies_to=list(changes.keys()),
        bound=None,  # SOFT — bias-only, never hard-rejects
        confidence=confidence_for(1),
        supporting_experiments=[experiment_id],
    )


def soft_lessons_prompt_block(lessons: List[Constraint]) -> str:
    """Prior-wins block injected into the planner prompt (bias only)."""
    soft = [c for c in lessons if c.bound is None]
    if not soft:
        return "(none)"
    return "\n".join(f"- {c.constraint_id}: {c.text}" for c in soft)


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
