"""Unit tests for the closed constraint loop (the hero, must not no-op).

Run: cd backend && python -m pytest app/loop/test_constraints.py -q
  or: python backend/app/loop/test_constraints.py   (no pytest needed)
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.loop.constraints import (  # noqa: E402
    learn_constraint_from_nan,
    violated_constraints,
    violates_bound,
)
from app.loop.planner import (  # noqa: E402
    NodeView, PlanContext, propose,
)
from app.loop.schemas import Bound, Constraint  # noqa: E402


def _lr_ban(value=0.01):
    return Constraint(
        constraint_id="learned_001", source="learned",
        text=f"ban lr>{value}", applies_to=["learning_rate"],
        bound=Bound(param="learning_rate", op=">", value=value),
        confidence="high", supporting_experiments=["exp_003"],
    )


def test_violates_bound_basic():
    c = _lr_ban(0.01)
    assert violates_bound({"learning_rate": 0.02}, c) is True
    assert violates_bound({"learning_rate": 0.011}, c) is True
    assert violates_bound({"learning_rate": 0.01}, c) is False  # boundary: > only
    assert violates_bound({"learning_rate": 0.004}, c) is False
    # change that doesn't touch the bounded param cannot violate
    assert violates_bound({"dropout": 0.9}, c) is False


def test_violates_bound_ops():
    assert violates_bound({"x": 5}, Constraint(constraint_id="c", source="human",
        text="", applies_to=["x"], bound=Bound(param="x", op=">=", value=5))) is True
    assert violates_bound({"x": 4}, Constraint(constraint_id="c", source="human",
        text="", applies_to=["x"], bound=Bound(param="x", op="<", value=5))) is True
    # prose-only constraint (no bound) never hard-rejects
    assert violates_bound({"x": 999}, Constraint(constraint_id="c", source="learned",
        text="be careful", applies_to=["x"])) is False


def test_deterministic_nan_rule():
    c = learn_constraint_from_nan(lr_at_failure=0.02, experiment_id="exp_003",
                                  constraint_id="learned_001")
    assert c.bound.param == "learning_rate"
    assert c.bound.op == ">"
    assert c.bound.value == 0.01  # x * 0.5
    assert c.source == "learned"
    assert "exp_003" in c.supporting_experiments


def test_planner_hard_rejects_and_retries_after_nan():
    """After a NaN at lr=0.02 with a learned bound lr>0.01, the planner must
    hard-reject a still-too-high candidate and propose a compliant LR whose
    rationale references the constraint."""
    constraint = learn_constraint_from_nan(lr_at_failure=0.02, experiment_id="exp_003",
                                           constraint_id="learned_001")
    best = NodeView(id="exp_002", operator="improve", status="success",
                    config={"learning_rate": 0.003, "scheduler": "cosine"},
                    changes={"scheduler": "cosine"},
                    final_metrics={"val_accuracy": 0.901})
    failed = NodeView(id="exp_003", operator="improve", status="failed",
                      config={"learning_rate": 0.02, "scheduler": "cosine"},
                      changes={"learning_rate": 0.02},
                      failure_type="nan_detected", parent_id="exp_002")
    ctx = PlanContext(nodes=[best, failed], constraints=[constraint],
                      allowed_changes=["learning_rate", "scheduler", "augmentation"],
                      baseline_config={"learning_rate": 0.01},
                      objective={"metric": "val_accuracy", "direction": "maximize"})
    res = propose(ctx, llm=None)
    lr = res.proposal.changes.get("learning_rate")
    assert lr is not None and not violates_bound({"learning_rate": lr}, constraint)
    assert len(res.rejected_candidates) >= 1  # a violating candidate was rejected
    assert "learned_001" in res.proposal.rationale
    assert not violated_constraints(res.proposal.changes, [constraint])


def test_draft_seed_first():
    ctx = PlanContext(nodes=[], constraints=[], allowed_changes=["learning_rate"],
                      baseline_config={"learning_rate": 0.01, "optimizer": "adam",
                                       "dropout": 0.25},
                      objective={"metric": "val_accuracy", "direction": "maximize"})
    res = propose(ctx, llm=None)
    assert res.proposal.operator == "draft"
    assert res.parent_id is None


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")


if __name__ == "__main__":
    _run_all()
