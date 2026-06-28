"""Loop-start seam for W3 / integration (kept deliberately loose).

Two ways the autonomous loop (W3) can be launched when a mission starts:

  1. In-process: W3 (or the lead during integration) calls register_loop_runner(fn).
     `fn(mission_id, mode)` is invoked on POST /missions/{id}/start. This is the
     preferred seam — no subprocess, no import cycle (the loop writes events via the
     event log per CONTRACT §6, never by importing the API layer).

  2. Subprocess fallback: if no runner is registered but backend/app/loop/run_mission.py
     exists, /start spawns `python -m app.loop.run_mission <mission_id> <mode>` detached.

Everything is guarded so the server runs fine before W3 lands (loop dir may not exist).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

# backend/app/api/loop_hook.py -> parents[2] == backend/, parents[3] == repo root
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[3]
_RUN_MISSION = _BACKEND_DIR / "app" / "loop" / "run_mission.py"

_runner: Optional[Callable[[str, str], None]] = None

# Best-effort registry of loops this server launched, so the stop endpoint can tell
# whether a loop is alive to honor the control file (in which case the LOOP emits
# mission_finished on stop) or whether the API must emit mission_finished itself
# (CONTRACT §5.1: "if no loop is running, the API emits it directly").
#   mission_id -> {"via": "in_process"|"subprocess", "proc": Popen | None}
_LAUNCHED: dict = {}


def register_loop_runner(fn: Callable[[str, str], None]) -> None:
    """W3/integration registers an in-process loop launcher: fn(mission_id, mode)."""
    global _runner
    _runner = fn


def start_loop(mission_id: str, mode: str) -> dict:
    """Best-effort launch of the loop. Never raises — returns a small status dict."""
    if _runner is not None:
        try:
            _runner(mission_id, mode)
            _LAUNCHED[mission_id] = {"via": "in_process", "proc": None}
            return {"loop": "started", "via": "in_process"}
        except Exception as exc:  # noqa: BLE001 - never let the API 500 on loop failure
            return {"loop": "error", "via": "in_process", "detail": str(exc)}

    if _RUN_MISSION.exists():
        try:
            proc = subprocess.Popen(
                [sys.executable, "-m", "app.loop.run_mission", mission_id, mode],
                cwd=str(_BACKEND_DIR),
            )
            _LAUNCHED[mission_id] = {"via": "subprocess", "proc": proc}
            return {"loop": "started", "via": "subprocess"}
        except Exception as exc:  # noqa: BLE001
            return {"loop": "error", "via": "subprocess", "detail": str(exc)}

    # No loop available yet (pre-W3). The mission_started event is still recorded.
    return {"loop": "not_available", "via": None}


def loop_running(mission_id: str) -> bool:
    """Best-effort: did THIS server launch a loop for the mission that is still alive?

    - subprocess: alive iff Popen.poll() is None.
    - in_process: we cannot poll a thread/coroutine, so assume alive once launched (the
      loop itself will then honor the control file and emit mission_finished on stop).
    - never launched here (e.g. pure Mode-B external, or pre-W3): False.
    """
    info = _LAUNCHED.get(mission_id)
    if not info:
        return False
    if info["via"] == "subprocess":
        proc = info.get("proc")
        return bool(proc is not None and proc.poll() is None)
    return True
