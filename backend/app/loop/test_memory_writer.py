"""Hermetic unit tests for the GATED LLM memory-writer (doc 11 #4).

NO real LLM calls — a FakeLLM stub returns canned strings. Covers the three
safety properties (soft-only/bound-stripped, flake->no-op, gated-off) + dedup.

Run: cd backend && source .venv/bin/activate && python app/loop/test_memory_writer.py
  or: python -m pytest app/loop/test_memory_writer.py -q
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.loop import memory_writer as MW  # noqa: E402
from app.loop.constraints import violated_constraints, violates_bound  # noqa: E402
from app.loop.planner import NodeView  # noqa: E402
from app.loop.schemas import Constraint  # noqa: E402


# --- test doubles -------------------------------------------------------------

class FakeLLM:
    """Stub LLMClient: returns a canned reply string from complete_json's parse.

    ``reply`` is what the real client would have parsed out of the model text:
    a dict (success), or None (no/garbage output). ``avail`` toggles
    available(). ``raises`` makes complete_json blow up (exception path).
    """

    def __init__(self, reply=None, avail=True, raises=False):
        self._reply = reply
        self._avail = avail
        self._raises = raises
        self.calls = 0

    def available(self):
        return self._avail

    def complete_json(self, system, user, max_tokens=600):
        self.calls += 1
        if self._raises:
            raise RuntimeError("boom")
        return self._reply


def _nodes():
    return [
        NodeView(id="exp_000", operator="draft", status="success",
                 config={"learning_rate": 0.01}, changes={},
                 final_metrics={"val_accuracy": 0.85}),
        NodeView(id="exp_001", operator="improve", status="success",
                 config={"learning_rate": 0.003, "scheduler": "cosine"},
                 changes={"scheduler": "cosine"},
                 final_metrics={"val_accuracy": 0.89}),
    ]


def _enable():
    os.environ["KUN_MEMORY_WRITER"] = "1"


def _disable():
    os.environ.pop("KUN_MEMORY_WRITER", None)


# --- 1. valid JSON -> soft Constraints (bound None, source/confidence) --------

def test_valid_json_yields_soft_constraints():
    _enable()
    llm = FakeLLM(reply={"lessons": [
        {"text": "cosine scheduling helped when the learning rate was low",
         "applies_to": ["scheduler", "learning_rate"]},
        {"text": "draft baseline was a reasonable starting point",
         "applies_to": []},
    ]})
    out = MW.distill_soft_lessons(nodes=_nodes(), existing_lessons=[], llm=llm)
    assert llm.calls == 1
    assert len(out) == 2
    for c in out:
        assert isinstance(c, Constraint)
        assert c.bound is None                     # SOFT tier
        assert c.source == "learned"
        assert c.confidence == "medium"            # confidence_for(1)
        assert "bound" not in c.to_payload()       # not serialized as a hard ban
    # sequential ids start at id_start+1
    assert out[0].constraint_id == "learned_001"
    assert out[1].constraint_id == "learned_002"
    # a no-bound lesson can NEVER hard-reject
    assert violated_constraints({"scheduler": "cosine"}, out) == []
    _disable()


def test_id_start_offsets_ids():
    _enable()
    llm = FakeLLM(reply={"lessons": [{"text": "lesson a", "applies_to": []}]})
    out = MW.distill_soft_lessons(nodes=_nodes(), existing_lessons=[], llm=llm,
                                  id_start=5)
    assert out[0].constraint_id == "learned_006"
    _disable()


# --- 2. LLM returns a bound/ban -> the bound is STRIPPED -----------------------

def test_llm_supplied_bound_is_stripped():
    _enable()
    # The model tries to author a hard ban with a numeric bound — must be dropped.
    llm = FakeLLM(reply={"lessons": [{
        "text": "ban high learning rate",
        "applies_to": ["learning_rate"],
        "bound": {"param": "learning_rate", "op": ">", "value": 0.01},
    }]})
    out = MW.distill_soft_lessons(nodes=_nodes(), existing_lessons=[], llm=llm)
    assert len(out) == 1
    assert out[0].bound is None                     # bound STRIPPED
    assert "bound" not in out[0].to_payload()
    # even the value the LLM tried to ban does not hard-reject
    assert violates_bound({"learning_rate": 0.99}, out[0]) is False
    _disable()


# --- 3. flake / malformed / unavailable -> [] and never raises ----------------

def test_none_reply_is_noop():
    _enable()
    out = MW.distill_soft_lessons(nodes=_nodes(), existing_lessons=[],
                                  llm=FakeLLM(reply=None))
    assert out == []
    _disable()


def test_malformed_shapes_are_noop():
    _enable()
    for bad in [
        {"lessons": "not a list"},
        {"lessons": [42, "x", None]},               # no dict items survive
        {"lessons": [{"applies_to": ["x"]}]},        # missing text
        {"lessons": [{"text": "   "}]},              # blank text
        ["not", "a", "dict"],                        # top-level not a dict
        {},                                           # empty
    ]:
        out = MW.distill_soft_lessons(nodes=_nodes(), existing_lessons=[],
                                      llm=FakeLLM(reply=bad))
        assert out == [], bad
    _disable()


def test_exception_is_noop():
    _enable()
    out = MW.distill_soft_lessons(nodes=_nodes(), existing_lessons=[],
                                  llm=FakeLLM(raises=True))
    assert out == []
    _disable()


def test_unavailable_llm_is_noop():
    _enable()
    llm = FakeLLM(reply={"lessons": [{"text": "x", "applies_to": []}]},
                  avail=False)
    out = MW.distill_soft_lessons(nodes=_nodes(), existing_lessons=[], llm=llm)
    assert out == [] and llm.calls == 0
    _disable()


def test_empty_trajectory_is_noop():
    _enable()
    llm = FakeLLM(reply={"lessons": [{"text": "x", "applies_to": []}]})
    out = MW.distill_soft_lessons(nodes=[], existing_lessons=[], llm=llm)
    assert out == [] and llm.calls == 0           # bails before calling the LLM
    _disable()


# --- 4. gating: off by default -------------------------------------------------

def test_gated_off_by_default():
    _disable()
    llm = FakeLLM(reply={"lessons": [{"text": "x", "applies_to": []}]})
    assert MW.enabled(llm) is False
    out = MW.distill_soft_lessons(nodes=_nodes(), existing_lessons=[], llm=llm)
    assert out == [] and llm.calls == 0


def test_enabled_requires_flag_and_availability():
    _disable()
    assert MW.enabled(FakeLLM(avail=True)) is False     # no flag
    _enable()
    assert MW.enabled(FakeLLM(avail=True)) is True
    assert MW.enabled(FakeLLM(avail=False)) is False    # flag but unavailable
    assert MW.enabled(None) is False
    _disable()


# --- 5. dedup against existing + within batch ----------------------------------

def test_dedup_against_existing_lessons():
    _enable()
    existing = [Constraint(
        constraint_id="learned_001", source="learned",
        text="Cosine scheduling helped when the learning rate was low",
        applies_to=["scheduler", "learning_rate"], bound=None, confidence="medium")]
    llm = FakeLLM(reply={"lessons": [
        # same text (case/space-insensitive) + same applies_to -> dropped
        {"text": "cosine scheduling helped when the LEARNING RATE was low  ",
         "applies_to": ["learning_rate", "scheduler"]},
        # genuinely new -> kept, id continues from id_start
        {"text": "smaller batches generalized better", "applies_to": ["batch_size"]},
    ]})
    out = MW.distill_soft_lessons(nodes=_nodes(), existing_lessons=existing,
                                  llm=llm, id_start=1)
    assert len(out) == 1
    assert out[0].text == "smaller batches generalized better"
    assert out[0].constraint_id == "learned_002"
    _disable()


def test_dedup_within_batch():
    _enable()
    llm = FakeLLM(reply={"lessons": [
        {"text": "augmentation helped", "applies_to": ["augmentation"]},
        {"text": "Augmentation  helped", "applies_to": ["augmentation"]},  # dup
    ]})
    out = MW.distill_soft_lessons(nodes=_nodes(), existing_lessons=[], llm=llm)
    assert len(out) == 1
    _disable()


def test_max_lessons_cap():
    _enable()
    llm = FakeLLM(reply={"lessons": [
        {"text": f"lesson number {i}", "applies_to": []} for i in range(10)
    ]})
    out = MW.distill_soft_lessons(nodes=_nodes(), existing_lessons=[], llm=llm)
    assert len(out) == MW.MAX_LESSONS
    _disable()


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")


if __name__ == "__main__":
    _run_all()
