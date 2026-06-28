"""Self-contained TestClient exercise of the P1 steering endpoints (CONTRACT §5.1/§9).

Run from backend/ with the repo venv:
    cd backend && source /Users/shivenmian/kun/backend/.venv/bin/activate
    python -m app.api.test_steering

It creates a mission, drives instruct/approve/reject/stop, reads GET /state, and asserts
events landed in the log + control.json was written + the §9.1 shape is correct. Writes go
to runs/<temp-mission-id>/ inside the worktree and are cleaned up at the end.
"""
from __future__ import annotations

import json
import shutil

from fastapi.testclient import TestClient

from app.api.control import control_path
from app.events import events_path
from app.main import app  # noqa: F401  (FastAPI app factory)

client = TestClient(app)


def _events(mission_id):
    return [json.loads(l) for l in events_path(mission_id).read_text().splitlines() if l.strip()]


def _types(mission_id):
    return [e["type"] for e in _events(mission_id)]


def main() -> None:
    # 1) create a mission + a proposed experiment via direct event append (no loop here)
    r = client.post(
        "/missions",
        json={
            "name": "steering-test",
            "goal": "g",
            "objective": {"metric": "val_accuracy", "direction": "maximize", "target": 0.9},
            "budget": {"max_experiments": 10},
        },
    )
    assert r.status_code == 200, r.text
    mission_id = r.json()["mission_id"]
    print(f"created mission {mission_id}")

    try:
        # seed a proposed experiment + a finished one + a hard constraint + a soft lesson
        from app.events import append_event

        append_event(
            "experiment_finished",
            {"status": "success", "final_metrics": {"val_accuracy": 0.81}},
            mission_id=mission_id,
            experiment_id="exp_001",
        )
        # NB: a finished node needs to be "valid" — finished sets that. give it a proposal too
        append_event(
            "experiment_proposed",
            {"operator": "improve", "changes": {"learning_rate": 0.01}, "hypothesis": "h"},
            mission_id=mission_id,
            experiment_id="exp_001",
        )
        append_event(
            "constraint_added",
            {
                "constraint_id": "c_hard",
                "source": "human",
                "text": "lr too high",
                "bound": {"param": "learning_rate", "op": ">", "value": 0.05},
            },
            mission_id=mission_id,
        )
        append_event(
            "constraint_learned",
            {
                "constraint_id": "c_soft",
                "source": "learned",
                "text": "augmentation helped",
            },
            mission_id=mission_id,
        )
        # a fork with no experiments yet -> should appear in pending_forks
        append_event(
            "fork_created",
            {"instruction": "explore dropout", "reason": "plateau"},
            mission_id=mission_id,
            branch_id="branch_fork1",
            parent_experiment_id="exp_001",
            actor={"type": "human", "name": "user"},
        )

        # 2) instruct
        r = client.post(
            f"/missions/{mission_id}/instruct",
            json={"text": "try cosine", "applies_from": "exp_002",
                  "bound": {"param": "dropout", "op": "<", "value": 0.1}},
        )
        assert r.status_code == 200, r.text
        instr_id = r.json()["instruction_id"]
        assert instr_id.startswith("instr_"), instr_id
        print(f"instruct -> {instr_id}")

        # 3) a NEW proposed experiment (exp_007) to test the approval gate
        append_event(
            "experiment_proposed",
            {"operator": "improve", "changes": {"dropout": 0.5}, "hypothesis": "h2"},
            mission_id=mission_id,
            experiment_id="exp_007",
        )

        # turn on the approval gate via stop endpoint (action resume keeps it running)
        r = client.post(
            f"/missions/{mission_id}/stop",
            json={"action": "resume", "approval_required": True},
        )
        assert r.status_code == 200, r.text
        assert r.json() == {"action": "resume", "run_state": "run"}, r.json()

        # control.json written atomically with the gate on
        ctrl = json.loads(control_path(mission_id).read_text())
        assert ctrl["run_state"] == "run" and ctrl["approval_required"] is True, ctrl
        assert "updated_at" in ctrl
        print(f"control.json = {ctrl}")

        # 4) GET /state -> pending_approval should be exp_007 (unresolved + gate on)
        st = client.get(f"/missions/{mission_id}/state").json()
        assert st["mission_id"] == mission_id
        assert st["run_state"] == "run", st["run_state"]
        assert st["approval_required"] is True
        assert [c["constraint_id"] for c in st["active_constraints"]] == ["c_hard"], st
        assert [c["constraint_id"] for c in st["soft_lessons"]] == ["c_soft"], st
        assert st["pending_approval"] is not None, st
        assert st["pending_approval"]["experiment_id"] == "exp_007", st["pending_approval"]
        assert st["pending_approval"]["operator"] == "improve"
        assert st["pending_approval"]["changes"] == {"dropout": 0.5}
        # instruction was emitted before exp_007 proposal -> consumed -> not pending
        assert st["pending_instructions"] == [], st["pending_instructions"]
        assert len(st["pending_forks"]) == 1 and st["pending_forks"][0]["branch_id"] == "branch_fork1", st
        assert st["best"]["experiment_id"] == "exp_001", st["best"]
        assert st["best"]["metric"]["value"] == 0.81, st["best"]
        print("GET /state shape OK (pending_approval=exp_007, tiers split, fork pending)")

        # 5) approve exp_007
        r = client.post(
            f"/missions/{mission_id}/experiments/exp_007/approve",
            json={"edited": True, "changes": {"dropout": 0.3}, "note": "ok"},
        )
        assert r.status_code == 200 and r.json() == {"ok": True}, r.text
        st = client.get(f"/missions/{mission_id}/state").json()
        assert st["pending_approval"] is None, "approval should clear pending"
        print("approve -> pending_approval cleared")

        # 6) reject (a different exp) -> event lands
        append_event("experiment_proposed", {"operator": "debug", "changes": {}},
                     mission_id=mission_id, experiment_id="exp_008")
        r = client.post(
            f"/missions/{mission_id}/experiments/exp_008/reject",
            json={"reason": "bad", "replacement_changes": {"dropout": 0.2}},
        )
        assert r.status_code == 200 and r.json() == {"ok": True}, r.text

        # 7) instruct again AFTER the last proposal -> should now be pending
        client.post(f"/missions/{mission_id}/instruct", json={"text": "later note"})
        st = client.get(f"/missions/{mission_id}/state").json()
        assert len(st["pending_instructions"]) == 1, st["pending_instructions"]
        assert st["pending_instructions"][0]["text"] == "later note"
        print("post-proposal instruct -> pending_instructions has 1")

        # 8) pause -> run_state view = "paused"
        r = client.post(f"/missions/{mission_id}/stop", json={"action": "pause"})
        assert r.json() == {"action": "pause", "run_state": "pause"}, r.json()
        # approval_required preserved (not passed) == True
        ctrl = json.loads(control_path(mission_id).read_text())
        assert ctrl["run_state"] == "pause" and ctrl["approval_required"] is True, ctrl
        st = client.get(f"/missions/{mission_id}/state").json()
        assert st["run_state"] == "paused", st["run_state"]
        print("pause -> run_state=paused, approval_required preserved")

        # 9) stop with NO loop running -> API emits mission_finished{reason:user_stop}
        assert "mission_finished" not in _types(mission_id)
        r = client.post(f"/missions/{mission_id}/stop", json={"action": "stop", "reason": "done"})
        assert r.json() == {"action": "stop", "run_state": "stop"}, r.json()
        evs = _events(mission_id)
        finished = [e for e in evs if e["type"] == "mission_finished"]
        assert len(finished) == 1, f"expected exactly one mission_finished, got {len(finished)}"
        assert finished[0]["payload"]["reason"] == "user_stop", finished[0]
        assert finished[0]["payload"]["best_experiment_id"] == "exp_001", finished[0]
        ctrl = json.loads(control_path(mission_id).read_text())
        assert ctrl["run_state"] == "stop", ctrl
        st = client.get(f"/missions/{mission_id}/state").json()
        assert st["run_state"] == "finished", st["run_state"]
        print("stop (no loop) -> mission_finished{user_stop} emitted; run_state=finished")

        # 10) double-stop must NOT emit a second mission_finished
        client.post(f"/missions/{mission_id}/stop", json={"action": "stop"})
        assert _types(mission_id).count("mission_finished") == 1, "double-stop dup-emitted"
        print("double-stop -> no duplicate mission_finished")

        # 11) assert all three steering event types landed in the log
        tset = set(_types(mission_id))
        for t in ("instruction_added", "experiment_approved", "experiment_rejected"):
            assert t in tset, f"missing {t}"
        print("all three steering event types present in log")

        print("\nALL STEERING TESTS PASSED")
    finally:
        run_dir = events_path(mission_id).parent
        if run_dir.exists():
            shutil.rmtree(run_dir)
            print(f"cleaned up {run_dir}")


if __name__ == "__main__":
    main()
