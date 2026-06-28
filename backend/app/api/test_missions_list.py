"""Self-contained TestClient exercise of the enriched GET /missions (CONTRACT §5.2).

Run from backend/ with the repo venv:
    cd backend && source /Users/shivenmian/kun/backend/.venv/bin/activate
    python -m app.api.test_missions_list

Creates two local missions, registers the nanogpt replay as an external mission, then asserts
GET /missions returns one §5.2 summary OBJECT per mission (mission_id/name/run_state/mode/
experiments_count/best/updated_at), the registered one reads mode="observe" with a non-zero
experiments_count + a best, and the list is sorted most-recently-updated first. Also checks the
robustness path: an empty mission log degrades to a minimal row instead of 500ing the endpoint.
Writes go to runs/<temp-mission-id>/ inside the worktree and are cleaned up at the end.
"""
from __future__ import annotations

import shutil
import time

from fastapi.testclient import TestClient

from app.events import append_event, events_path
from app.main import app

client = TestClient(app)

REPLAY = "/Users/shivenmian/kun/examples/replays/nanogpt.events.jsonl"
SUMMARY_FIELDS = {
    "mission_id",
    "name",
    "run_state",
    "mode",
    "experiments_count",
    "best",
    "updated_at",
}


def _create_mission(name: str) -> str:
    r = client.post(
        "/missions",
        json={
            "name": name,
            "goal": "g",
            "objective": {"metric": "val_accuracy", "direction": "maximize", "target": 0.9},
            "budget": {"max_experiments": 10},
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["mission_id"]


def main() -> None:
    created: list[str] = []
    registered_id = "ext_nano_" + str(int(time.time()))
    empty_id = "empty_mission_" + str(int(time.time()))

    try:
        # 1) two local missions, with a finished experiment on the second so it has a best
        m1 = _create_mission("First Sprint")
        created.append(m1)
        time.sleep(1.05)  # ensure m2's last timestamp is strictly later (1s clock resolution)
        m2 = _create_mission("Second Sprint")
        created.append(m2)
        append_event(
            "experiment_proposed",
            {"operator": "draft", "changes": {"learning_rate": 0.01}, "hypothesis": "h"},
            mission_id=m2,
            experiment_id="exp_001",
        )
        append_event(
            "experiment_finished",
            {"status": "success", "final_metrics": {"val_accuracy": 0.88}},
            mission_id=m2,
            experiment_id="exp_001",
        )

        # 2) register the nanogpt replay as an external mission
        r = client.post("/missions/register", json={"mission_id": registered_id, "events_path": REPLAY})
        assert r.status_code == 200, r.text

        # 3) an empty-log mission (robustness): create the dir + empty events.jsonl
        ep = events_path(empty_id)
        ep.parent.mkdir(parents=True, exist_ok=True)
        ep.write_text("")
        created.append(empty_id)

        # --- GET /missions ---
        r = client.get("/missions")
        assert r.status_code == 200, r.text
        missions = r.json()["missions"]
        assert isinstance(missions, list)
        by_id = {m["mission_id"]: m for m in missions}

        # every row is an object with exactly the §5.2 fields
        for m in missions:
            assert isinstance(m, dict), m
            assert set(m.keys()) == SUMMARY_FIELDS, m

        # local mission rows
        assert by_id[m1]["name"] == "First Sprint"
        assert by_id[m1]["run_state"] == "run"
        assert by_id[m1]["mode"] is None  # never started
        assert by_id[m1]["experiments_count"] == 0
        assert by_id[m1]["best"] is None

        assert by_id[m2]["experiments_count"] == 1
        assert by_id[m2]["best"] == {
            "experiment_id": "exp_001",
            "metric": {"name": "val_accuracy", "value": 0.88},
        }

        # registered external mission: observe mode, real experiments + best from the replay
        reg = by_id[registered_id]
        assert reg["mode"] == "observe", reg
        assert reg["experiments_count"] > 0, reg
        assert reg["run_state"] == "finished", reg  # replay ends with mission_finished
        assert reg["best"] is not None and reg["best"]["experiment_id"], reg
        assert reg["updated_at"] == "2026-06-27T20:01:14Z", reg

        # robustness: the empty-log mission appears as a minimal row, no 500
        emp = by_id[empty_id]
        assert emp["experiments_count"] == 0 and emp["name"] is None
        assert emp["run_state"] == "run" and emp["updated_at"] is None

        # sorted most-recently-updated first (updated_at descending, None last)
        tss = [m["updated_at"] or "" for m in missions]
        assert tss == sorted(tss, reverse=True), tss
        # concretely: m2 (later) precedes m1 in the list
        assert missions.index(by_id[m2]) < missions.index(by_id[m1])

        print(f"PASS: GET /missions returned {len(missions)} §5.2 summary rows, sorted desc")
    finally:
        for mid in created:
            shutil.rmtree(events_path(mid).parent, ignore_errors=True)


if __name__ == "__main__":
    main()
