"""Mode-B external loop with the FEEDBACK CHANNEL (P1 scope #5).

Like external_loop_demo.py this is somebody else's optimizer loop whose ONLY Kun
integration is `kun_log(...)` — EXCEPT it also READS BACK Kun's steering by polling
`GET /missions/{id}/state` at the top of each iteration and OBEYING it (CONTRACT §9.1).
That is what gives the cockpit *teeth over an external loop*: a human adds a constraint
or instruction in Kun, and this not-Kun loop honors it on its next proposal.

The producer side stays tiny — kun_log to emit + one HTTP GET to read /state. No backend
import, no Kun internals.

Run (with the backend up):
  KUN_MODE_B_MISSION=mission_mode_b python examples/external_loop_mode_b.py
Then in another shell, steer it live, e.g.:
  curl -s -X POST localhost:8000/missions/mission_mode_b/instruct \
       -d '{"text":"keep lr small","bound":{"param":"learning_rate","op":">","value":0.002}}'
…and watch the loop clamp its learning_rate on the next iteration.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time
import urllib.request as _u
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from kun.log import kun_log  # emit surface (unchanged from the pure wedge)


def obey_state(changes: Dict[str, Any], state: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Adjust a proposed ``changes`` dict so it honors Kun's active steering.

    PURE + testable (no I/O). For every active HARD constraint (one with a
    structured ``bound``) that ``changes`` would violate, move the offending value
    to the legal side of the bound. Pending instructions are surfaced as notes
    (advisory bias). Returns ``(adjusted_changes, notes)``.
    """
    adjusted = dict(changes)
    notes: List[str] = []

    # HARD enforcement: a structured `bound` hard-rejects, whether it arrived as a
    # learned/human constraint (active_constraints) OR as a steering instruction
    # carrying a bound (pending_instructions) — the Mode-B mirror of CONTRACT §9.3.
    bounded: List[Dict[str, Any]] = []
    for c in state.get("active_constraints", []) or []:
        if c.get("bound"):
            bounded.append({"id": c.get("constraint_id", "?"), "bound": c["bound"]})
    for ins in state.get("pending_instructions", []) or []:
        if ins.get("bound"):
            bounded.append({"id": ins.get("instruction_id", "?"), "bound": ins["bound"]})
        elif ins.get("text"):
            notes.append(f"instruction {ins.get('instruction_id', '?')}: {ins['text']}")  # advisory bias

    for item in bounded:
        b = item["bound"]
        param, op = b.get("param"), b.get("op")
        if param not in adjusted:
            continue
        try:
            v = float(adjusted[param])
            lim_f = float(b.get("value"))
        except (TypeError, ValueError):
            continue
        banned = (
            (op == ">" and v > lim_f) or (op == ">=" and v >= lim_f)
            or (op == "<" and v < lim_f) or (op == "<=" and v <= lim_f)
        )
        if not banned:
            continue
        # Move to a clearly-legal value on the allowed side of the ban.
        adjusted[param] = round(lim_f * 0.5, 8) if op in (">", ">=") else round(lim_f * 2, 8)
        notes.append(f"obeyed {item['id']}: clamped {param} {v} -> {adjusted[param]}")
    return adjusted, notes


def fetch_state(base: str, mission_id: str) -> Dict[str, Any]:
    """GET /missions/{id}/state; return {} on any error (advisory channel)."""
    try:
        with _u.urlopen(f"{base}/missions/{mission_id}/state", timeout=5) as r:
            return json.loads(r.read() or "{}")
    except Exception:
        return {}


def register(base: str, mission_id: str, events_path: str) -> None:
    try:
        body = json.dumps({"mission_id": mission_id, "events_path": events_path}).encode()
        req = _u.Request(f"{base}/missions/register", data=body,
                         headers={"Content-Type": "application/json"}, method="POST")
        _u.urlopen(req, timeout=5).read()
    except Exception as e:
        print(f"[mode-b] register skipped ({e})", flush=True)


def main() -> None:
    mid = os.environ.get("KUN_MODE_B_MISSION", "mission_mode_b")
    base = os.environ.get("KUN_BACKEND", "http://localhost:8000").rstrip("/")
    iters = int(os.environ.get("KUN_MODE_B_ITERS", "6"))
    events_path = os.path.abspath(f"runs/{mid}/events.jsonl")
    os.makedirs(os.path.dirname(events_path), exist_ok=True)
    os.environ.setdefault("KUN_EVENTS", events_path)

    kun_log("mission_created",
            {"name": "External loop (Mode-B, obeys Kun)", "goal": "my optimizer, steered by Kun",
             "objective": {"metric": "val_accuracy", "direction": "maximize"}}, mission_id=mid)
    kun_log("mission_started", {"mode": "live", "started_by": "external_script"}, mission_id=mid)
    register(base, mid, events_path)  # so GET /state serves this externally-produced mission

    best = 0.0
    for i in range(iters):
        eid = f"ext_{i:03d}"
        parent = f"ext_{i - 1:03d}" if i else None
        # 1) READ BACK Kun's steering and OBEY it (the feedback channel).
        state = fetch_state(base, mid)
        # 2) My own proposal — deliberately wants a largish lr; Kun may clamp it.
        my_changes = {"learning_rate": round(0.01 / (i + 1), 6), "dropout": 0.3}
        changes, notes = obey_state(my_changes, state)
        for n in notes:
            print(f"[mode-b] {eid}: {n}", flush=True)
        acc = round(0.85 + 0.01 * i, 4)
        env = {"mission_id": mid, "experiment_id": eid, "parent_experiment_id": parent}
        kun_log("experiment_proposed",
                {"operator": "improve", "hypothesis": f"tweak #{i}", "changes": changes,
                 "rationale": "; ".join(notes) or "no active steering"}, **env)
        kun_log("experiment_started", {"command": "my_own_trainer.py"}, **env)
        kun_log("metric_logged", {"name": "val_accuracy", "value": acc, "step": 1}, **env)
        kun_log("experiment_finished", {"status": "success", "final_metrics": {"val_accuracy": acc}}, **env)
        best = max(best, acc)
        time.sleep(float(os.environ.get("KUN_MODE_B_SLEEP", "1.5")))

    kun_log("mission_finished",
            {"status": "completed", "best_metric": {"name": "val_accuracy", "value": best}},
            mission_id=mid)
    print(f"done -> {events_path}", flush=True)


if __name__ == "__main__":
    main()
