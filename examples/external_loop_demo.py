"""Asset C — a genuinely-NOT-Kun external loop. The wedge proof (demo Beat 2).

This is somebody else's optimizer loop. The ONLY Kun integration is the `kun_log(...)`
calls — ~5 lines. Run it while the cockpit watches and the nodes appear live, proving
Kun observes loops it never ran.

  KUN_EVENTS=runs/ext_demo/events.jsonl python examples/external_loop_demo.py
"""
import os
import pathlib
import random
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from kun.log import kun_log  # the entire integration surface

os.makedirs("runs/ext_demo", exist_ok=True)
os.environ.setdefault("KUN_EVENTS", "runs/ext_demo/events.jsonl")

MID = "mission_external_demo"
best = 0.0

kun_log("mission_created",
        {"name": "External loop (not Kun)", "goal": "my own optimizer",
         "objective": {"metric": "val_accuracy", "direction": "maximize"}},
        mission_id=MID)
kun_log("mission_started", {"mode": "live", "started_by": "external_script"}, mission_id=MID)

for i in range(5):
    eid = f"ext_{i:03d}"
    acc = round(0.85 + 0.012 * i + random.uniform(-0.004, 0.004), 4)  # pretend our optimizer improved
    kun_log("experiment_proposed",
            {"operator": "improve", "hypothesis": f"my tweak #{i}", "changes": {"lr": 0.003 / (i + 1)}},
            mission_id=MID, experiment_id=eid)
    kun_log("experiment_started", {"command": "my_own_trainer.py"}, mission_id=MID, experiment_id=eid)
    kun_log("metric_logged", {"name": "val_accuracy", "value": acc, "step": 1}, mission_id=MID, experiment_id=eid)
    kun_log("experiment_finished", {"status": "success", "final_metrics": {"val_accuracy": acc}},
            mission_id=MID, experiment_id=eid)
    best = max(best, acc)
    time.sleep(1.5)  # so nodes appear live in the cockpit

kun_log("mission_finished",
        {"status": "completed", "best_metric": {"name": "val_accuracy", "value": best}},
        mission_id=MID)
print(f"done -> {os.environ['KUN_EVENTS']} (watch these appear live in Kun)")
