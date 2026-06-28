"""Strict schemas for LLM-driven loop outputs + the canonical constraint object.

The planner / evaluator / decider ask the LLM for JSON; we validate it here. On
invalid output the caller retries once, then falls back to the heuristic path.
Pydantic v2.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


Operator = Literal["draft", "debug", "improve"]
Decision = Literal[
    "continue_branch", "promote", "reject", "retry_debug", "fork", "stop"
]


class Proposal(BaseModel):
    """LLM planner output -> experiment_proposed payload (minus envelope)."""

    operator: Operator
    hypothesis: str
    changes: Dict[str, Any] = Field(default_factory=dict)
    expected_outcome: Optional[str] = None
    risk: Optional[str] = None
    rationale: str

    @field_validator("changes")
    @classmethod
    def _no_empty_for_improve(cls, v, info):  # noqa: D401
        # An improve/debug step that changes nothing is meaningless.
        return v


class Evaluation(BaseModel):
    """LLM evaluator output -> evaluation_created payload."""

    verdict: Literal["promote", "reject", "neutral"]
    summary: str
    evidence: List[str] = Field(default_factory=list)
    concerns: List[str] = Field(default_factory=list)


class NextAction(BaseModel):
    type: str = "propose_next_experiment"
    parent_experiment_id: Optional[str] = None


class DecisionOut(BaseModel):
    """LLM decider output -> decision_created payload."""

    decision: Decision
    rationale: str
    next_action: NextAction = Field(default_factory=NextAction)


class Bound(BaseModel):
    """The machine-checkable banned region. ``op`` is the *banned* direction."""

    param: str
    op: Literal[">", ">=", "<", "<=", "=="]
    value: float


class Constraint(BaseModel):
    """Canonical constraint object (CONTRACT §3). Shared by added/learned."""

    constraint_id: str
    source: Literal["human", "learned"]
    text: str
    applies_to: List[str] = Field(default_factory=list)
    bound: Optional[Bound] = None
    confidence: Optional[Literal["low", "medium", "high"]] = None
    supporting_experiments: List[str] = Field(default_factory=list)

    def to_payload(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "constraint_id": self.constraint_id,
            "source": self.source,
            "text": self.text,
            "applies_to": self.applies_to,
        }
        if self.bound is not None:
            d["bound"] = self.bound.model_dump()
        if self.source == "learned":
            d["confidence"] = self.confidence or "medium"
            d["supporting_experiments"] = self.supporting_experiments
        return d
