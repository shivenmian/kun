"""Hermetic tests for the Mode-B feedback channel obedience logic (obey_state)."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from external_loop_mode_b import obey_state


def test_clamps_violating_value():
    state = {"active_constraints": [
        {"constraint_id": "learned_001",
         "bound": {"param": "learning_rate", "op": ">", "value": 0.002}}]}
    adj, notes = obey_state({"learning_rate": 0.01, "dropout": 0.3}, state)
    assert adj["learning_rate"] <= 0.002, adj
    assert adj["dropout"] == 0.3            # untouched param preserved
    assert any("learned_001" in n for n in notes)


def test_non_violating_unchanged():
    state = {"active_constraints": [
        {"bound": {"param": "learning_rate", "op": ">", "value": 0.05}}]}
    adj, notes = obey_state({"learning_rate": 0.01}, state)
    assert adj["learning_rate"] == 0.01
    assert notes == []


def test_soft_lesson_never_clamps():
    # a constraint with NO bound (soft lesson) must not change anything
    state = {"active_constraints": [{"constraint_id": "learned_003", "text": "cosine helped"}]}
    adj, notes = obey_state({"learning_rate": 0.01}, state)
    assert adj == {"learning_rate": 0.01}


def test_instruction_surfaced_as_note():
    state = {"pending_instructions": [{"instruction_id": "instr_1", "text": "try cosine"}]}
    adj, notes = obey_state({"learning_rate": 0.01}, state)
    assert any("try cosine" in n for n in notes)


def test_instruction_bound_is_enforced():
    # an instruction carrying a structured bound hard-clamps (CONTRACT §9.3 mirror)
    state = {"pending_instructions": [
        {"instruction_id": "instr_2", "text": "keep lr small",
         "bound": {"param": "learning_rate", "op": ">", "value": 0.003}}]}
    adj, notes = obey_state({"learning_rate": 0.01}, state)
    assert adj["learning_rate"] == 0.0015, adj      # lim*0.5, not coincidence
    assert any("instr_2" in n and "clamped" in n for n in notes)


def test_empty_state_is_noop():
    adj, notes = obey_state({"learning_rate": 0.01}, {})
    assert adj == {"learning_rate": 0.01} and notes == []


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
