"""LLM "memory writer" — the GATED, additive SOFT-lesson distiller (doc 11 #4).

This is the OPTIONAL, nondeterministic enrichment on top of the deterministic
memory spine (NaN->LR, underfit->dropout, merge/confidence, positive
Σ-summaries). It asks the LLM to distill a few DURABLE, general SOFT lessons
from the trajectory so far ("cosine scheduling helped when LR was low").

Three safety properties — all enforced HERE, none rely on the caller:

  1. SOFT-only / bound-stripped. Every distilled lesson becomes a ``Constraint``
     with ``bound=None`` (CONTRACT §3/§9.4: LLM-authored memory is soft-tier and
     can NEVER hard-reject). We construct the Constraint with ``bound=None``
     unconditionally, so even if the LLM returns a ``bound``/numeric ban it is
     simply never read — it cannot leak into the hard tier.

  2. Never-hurt / flake -> no-op. The whole pass is wrapped so ANY failure (no
     key, llm unavailable, malformed/non-JSON output, exception) returns ``[]``
     and never raises into the loop. The deterministic spine is unaffected.

  3. Gated off by default. ``enabled()`` is True only when the env flag is set
     AND the llm is available — so with ``KUN_MEMORY_WRITER`` unset the loop is
     byte-for-byte unchanged.

No new event types: the caller emits each lesson as ``constraint_learned`` with
no bound, exactly like the deterministic soft Σ-summaries.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from .constraints import confidence_for
from .schemas import Constraint

# Hard cap on how many lessons we accept from one pass (defensive — keeps the
# panel readable and bounds token/work regardless of what the LLM returns).
MAX_LESSONS = 3

_SYSTEM = (
    "You are the research-memory writer for an autonomous ML experiment loop. "
    "Given the experiment trajectory and the lessons already recorded, distill a "
    "few DURABLE, GENERAL lessons that would help plan future experiments "
    "(e.g. 'cosine scheduling helped when the learning rate was low', "
    "'raising batch_size past 256 hurt throughput with no accuracy gain'). "
    "Rules: (1) lessons must be general takeaways, not one-off observations; "
    "(2) do NOT propose bans, bounds, thresholds, or numbers-as-prohibitions — "
    "these are soft biasing hints only; (3) do not repeat a lesson already "
    "recorded. "
    'Respond with STRICT JSON, an object of this exact shape: '
    '{"lessons": [{"text": "<concise lesson>", "applies_to": ["<param>", ...]}]}. '
    "Return at most " + str(MAX_LESSONS) + " lessons; return "
    '{"lessons": []} if nothing durable can be said.'
)


def enabled(llm) -> bool:
    """Gate: only run when explicitly opted in AND the llm is usable.

    With ``KUN_MEMORY_WRITER`` unset this is False, so the loop behaves exactly
    as it does today (the deterministic hero demo is never perturbed).
    """
    if os.environ.get("KUN_MEMORY_WRITER") != "1":
        return False
    try:
        return bool(llm is not None and llm.available())
    except Exception:
        return False


def _node_summary(node) -> Dict[str, Any]:
    """Compact, JSON-safe view of one trajectory node for the prompt."""
    return {
        "id": getattr(node, "id", None),
        "operator": getattr(node, "operator", None),
        "status": getattr(node, "status", None),
        "changes": getattr(node, "changes", {}) or {},
        "final_metrics": getattr(node, "final_metrics", {}) or {},
        "failure_type": getattr(node, "failure_type", None),
    }


def _norm(text: str) -> str:
    return " ".join(str(text).split()).strip().lower()


def _key(text: str, applies_to: List[str]) -> tuple:
    return (_norm(text), tuple(sorted(_norm(a) for a in applies_to)))


def distill_soft_lessons(
    *,
    nodes: List[Any],
    existing_lessons: List[Constraint],
    llm,
    id_start: int = 0,
    max_lessons: int = MAX_LESSONS,
) -> List[Constraint]:
    """Distill durable SOFT lessons from the trajectory via the LLM.

    Returns a list of ``Constraint`` with ``bound=None`` (soft tier),
    ``source="learned"``, ``confidence=confidence_for(1)``, and sequential ids
    ``learned_{id_start+1:03d}`` ... (only the SURVIVORS of dedup get ids, so the
    caller can ``learned_counter += len(result)``).

    NEVER raises and NEVER returns a bounded constraint. On any problem (gate
    off, unavailable llm, malformed/non-JSON output, exception) returns ``[]``.
    """
    try:
        if not enabled(llm):
            return []

        trajectory = [_node_summary(n) for n in nodes]
        if not trajectory:
            return []
        prior = [c.text for c in existing_lessons if c.bound is None]

        import json

        user = (
            "Trajectory so far (each node = one experiment):\n"
            + json.dumps(trajectory, default=str)
            + "\n\nLessons already recorded (do NOT repeat these):\n"
            + (json.dumps(prior) if prior else "(none)")
        )

        data = llm.complete_json(_SYSTEM, user, max_tokens=600)
        if not isinstance(data, dict):
            return []

        raw = data.get("lessons")
        if raw is None and "text" in data:  # tolerate a single-lesson object
            raw = [data]
        if not isinstance(raw, list):
            return []

        # Seed the dedup set with existing soft lessons (and dedup within batch).
        seen = {
            _key(c.text, c.applies_to)
            for c in existing_lessons
            if c.bound is None
        }

        out: List[Constraint] = []
        for item in raw:
            if len(out) >= max_lessons:
                break
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            applies_raw = item.get("applies_to") or []
            applies_to = [str(a) for a in applies_raw if isinstance(a, (str, int, float))]
            k = _key(text, applies_to)
            if k in seen:
                continue
            seen.add(k)
            cid = f"learned_{id_start + len(out) + 1:03d}"
            # CRITICAL: bound=None ALWAYS. Any 'bound'/ban the LLM returned is
            # ignored — a memory-writer lesson can never carry a bound.
            out.append(
                Constraint(
                    constraint_id=cid,
                    source="learned",
                    text=text.strip(),
                    applies_to=applies_to,
                    bound=None,
                    confidence=confidence_for(1),
                    supporting_experiments=[],
                )
            )
        return out
    except Exception:
        # Never-hurt invariant: any failure is a silent no-op.
        return []
