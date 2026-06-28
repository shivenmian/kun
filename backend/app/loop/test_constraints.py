"""Unit tests for the closed constraint loop (the hero, must not no-op).

Run: cd backend && python -m pytest app/loop/test_constraints.py -q
  or: python backend/app/loop/test_constraints.py   (no pytest needed)
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.loop.constraints import (  # noqa: E402
    confidence_for,
    detect_underfit_param,
    learn_constraint_from_nan,
    learn_constraint_from_underfit,
    merge_learned_constraint,
    soft_lesson_from_promotion,
    soft_lessons_prompt_block,
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


# --- underfitting -> dropout bound generator (sample's learned_002) -----------

def test_underfit_fires_when_train_and_val_both_drop():
    """dropout UP and BOTH train & val accuracy drop -> underfit signature."""
    hit = detect_underfit_param(
        changes={"dropout": 0.5},
        parent_config={"dropout": 0.25},
        parent_metrics={"val_accuracy": 0.912, "train_accuracy": 0.93},
        child_metrics={"val_accuracy": 0.881, "train_accuracy": 0.85},
    )
    assert hit == ("dropout", 0.5)
    c = learn_constraint_from_underfit(
        param=hit[0], value_at_underfit=hit[1],
        experiment_id="exp_006", constraint_id="learned_002",
    )
    assert c.bound.param == "dropout"
    assert c.bound.op == ">"
    assert c.bound.value == 0.4  # 0.5 * 0.8 -> mirrors sample learned_002
    assert c.source == "learned"
    assert c.confidence == "medium"  # single supporting experiment
    assert c.supporting_experiments == ["exp_006"]


def test_underfit_does_not_fire_boundaries():
    base_parent = {"dropout": 0.25}
    pm = {"val_accuracy": 0.912, "train_accuracy": 0.93}
    # val IMPROVED -> not underfitting (regularization helped)
    assert detect_underfit_param(
        changes={"dropout": 0.5}, parent_config=base_parent, parent_metrics=pm,
        child_metrics={"val_accuracy": 0.915, "train_accuracy": 0.92}) is None
    # train dropped but val rose -> overfitting fix, not underfit
    assert detect_underfit_param(
        changes={"dropout": 0.5}, parent_config=base_parent, parent_metrics=pm,
        child_metrics={"val_accuracy": 0.92, "train_accuracy": 0.90}) is None
    # regularization went DOWN -> never an underfit ban
    assert detect_underfit_param(
        changes={"dropout": 0.1}, parent_config=base_parent, parent_metrics=pm,
        child_metrics={"val_accuracy": 0.80, "train_accuracy": 0.80}) is None
    # a non-regularizer changed (lr) -> not this generator's concern
    assert detect_underfit_param(
        changes={"learning_rate": 0.02}, parent_config={"learning_rate": 0.003},
        parent_metrics=pm,
        child_metrics={"val_accuracy": 0.80, "train_accuracy": 0.80}) is None


# --- memory hygiene: merge + confidence growth --------------------------------

def test_confidence_growth_thresholds():
    assert confidence_for(0) == "low"
    assert confidence_for(1) == "medium"
    assert confidence_for(2) == "high"
    assert confidence_for(5) == "high"


def test_two_nans_same_param_merge_to_one_sharpened_constraint():
    active = []
    c1 = learn_constraint_from_nan(lr_at_failure=0.02, experiment_id="exp_003",
                                   constraint_id="learned_001")
    m1, merged1 = merge_learned_constraint(active, c1)
    assert merged1 is False and len(active) == 1
    # second NaN, lower lr -> tighter bound, same param
    c2 = learn_constraint_from_nan(lr_at_failure=0.01, experiment_id="exp_007",
                                   constraint_id="learned_002")
    m2, merged2 = merge_learned_constraint(active, c2)
    assert merged2 is True
    assert len(active) == 1                       # ONE constraint, not two
    assert active[0].constraint_id == "learned_001"  # stable id reused
    assert active[0].bound.value == 0.005         # tightened to min(0.01, 0.005)
    assert set(active[0].supporting_experiments) == {"exp_003", "exp_007"}
    assert active[0].confidence == "high"         # >=2 evidence


def test_merge_confidence_rises_medium_to_high():
    active = []
    u1 = learn_constraint_from_underfit(param="dropout", value_at_underfit=0.5,
                                        experiment_id="exp_006", constraint_id="learned_001")
    _, merged1 = merge_learned_constraint(active, u1)
    assert merged1 is False
    assert active[0].confidence == "medium"       # 1 supporting exp
    u2 = learn_constraint_from_underfit(param="dropout", value_at_underfit=0.45,
                                        experiment_id="exp_010", constraint_id="learned_002")
    _, merged2 = merge_learned_constraint(active, u2)
    assert merged2 is True
    assert len(active) == 1
    assert active[0].confidence == "high"         # rose medium -> high
    assert active[0].bound.value == 0.36          # min(0.4, 0.36)


def test_merge_different_param_appends():
    active = []
    merge_learned_constraint(active, learn_constraint_from_nan(
        lr_at_failure=0.02, experiment_id="exp_003", constraint_id="learned_001"))
    _, merged = merge_learned_constraint(active, learn_constraint_from_underfit(
        param="dropout", value_at_underfit=0.5, experiment_id="exp_006",
        constraint_id="learned_002"))
    assert merged is False
    assert len(active) == 2                         # different params -> separate


# --- positive Σ-summary soft lessons (SOFT tier) ------------------------------

def test_soft_lesson_has_no_bound_and_never_hard_rejects():
    lesson = soft_lesson_from_promotion(
        changes={"scheduler": "cosine"}, metric="val_accuracy", delta=0.012,
        experiment_id="exp_002", constraint_id="learned_003")
    assert lesson.bound is None                     # SOFT: bias-only
    assert lesson.source == "learned"
    assert lesson.text == "cosine: +0.012 val_accuracy"
    # a no-bound lesson can NEVER hard-reject any change
    assert violates_bound({"scheduler": "cosine"}, lesson) is False
    assert violated_constraints({"dropout": 999}, [lesson]) == []
    assert "bound" not in lesson.to_payload()       # not serialized as a hard ban


def test_soft_lessons_prompt_block_filters_to_no_bound():
    soft = soft_lesson_from_promotion(
        changes={"scheduler": "cosine"}, metric="val_accuracy", delta=0.012,
        experiment_id="exp_002", constraint_id="learned_003")
    hard = _lr_ban(0.01)  # has a bound -> excluded
    block = soft_lessons_prompt_block([soft, hard])
    assert "learned_003" in block and "cosine" in block
    assert "learned_001" not in block               # hard ban not a soft lesson


def test_planner_references_prior_win_in_rationale():
    """A later heuristic proposal's rationale should reference a soft lesson."""
    win = soft_lesson_from_promotion(
        changes={"learning_rate": 0.003}, metric="val_accuracy", delta=0.016,
        experiment_id="exp_001", constraint_id="learned_001")
    best = NodeView(id="exp_001", operator="improve", status="success",
                    config={"learning_rate": 0.003}, changes={"learning_rate": 0.003},
                    final_metrics={"val_accuracy": 0.889})
    ctx = PlanContext(nodes=[best], constraints=[], soft_lessons=[win],
                      allowed_changes=["scheduler", "augmentation", "learning_rate"],
                      baseline_config={"learning_rate": 0.01},
                      objective={"metric": "val_accuracy", "direction": "maximize"})
    res = propose(ctx, llm=None)
    assert "learned_001" in res.proposal.rationale   # builds on the prior win


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")


if __name__ == "__main__":
    _run_all()
