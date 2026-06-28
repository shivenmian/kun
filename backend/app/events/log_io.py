"""Event log I/O — the single read/append surface over runs/<mission_id>/events.jsonl.

CONTRACT §8.1/§8.3: appends go through kun_log (the only emit helper); the per-mission
log path is runs/<mission_id>/events.jsonl. Paths are resolved against the repo root so
the backend works whether launched from the repo root or from backend/.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# backend/app/events/log_io.py -> parents[3] == repo root (the worktree).
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# kun_log is the ONE emit helper (CONTRACT §8.3) — never write JSONL any other way.
from kun.log import kun_log  # noqa: E402

RUNS_DIR = REPO_ROOT / "runs"
SAMPLE_EVENTS = REPO_ROOT / "examples" / "replays" / "sample.events.jsonl"

# Registry of externally-produced missions whose log lives at a non-default path
# (CONTRACT §8.2 POST /missions/register). mission_id -> absolute events path.
_REGISTERED: Dict[str, str] = {}


def default_events_path(mission_id: str) -> Path:
    """runs/<mission_id>/events.jsonl (CONTRACT §8.1)."""
    return RUNS_DIR / mission_id / "events.jsonl"


def events_path(mission_id: str) -> Path:
    """Resolve the on-disk log for a mission, honoring register() overrides."""
    override = _REGISTERED.get(mission_id)
    if override:
        return Path(override)
    return default_events_path(mission_id)


def register_mission(mission_id: str, path: Optional[str] = None) -> Path:
    """Record an externally-produced mission so /stream + state can serve it.

    Defaults events_path to runs/<mission_id>/events.jsonl (CONTRACT §8.2). A given
    `path` that is NOT absolute is resolved against the repo root (REPO_ROOT), so callers
    can register bundled replays by repo-relative path (e.g.
    examples/replays/nanogpt.events.jsonl) regardless of the backend's CWD; absolute paths
    are used as-is. The parent dir is created so a tailer can start before the producer
    writes its first line.
    """
    if path:
        resolved = Path(path)
        if not resolved.is_absolute():
            resolved = REPO_ROOT / resolved
        _REGISTERED[mission_id] = str(resolved)
    else:
        resolved = default_events_path(mission_id)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def mission_exists(mission_id: str) -> bool:
    return events_path(mission_id).exists() or mission_id in _REGISTERED


def list_missions() -> List[str]:
    """Known mission ids: every runs/<id>/events.jsonl plus registered ids."""
    ids = set(_REGISTERED.keys())
    if RUNS_DIR.exists():
        for child in RUNS_DIR.iterdir():
            if child.is_dir() and (child / "events.jsonl").exists():
                ids.add(child.name)
    return sorted(ids)


def append_event(
    event_type: str,
    payload: Dict[str, Any],
    mission_id: str,
    **envelope: Any,
) -> Dict[str, Any]:
    """Append one event to the mission log via kun_log (auto dir-make + envelope fill)."""
    path = events_path(mission_id)
    return kun_log(
        event_type,
        payload,
        path=str(path),
        mission_id=mission_id,
        **envelope,
    )


def read_events_file(path: Path) -> List[Dict[str, Any]]:
    """Read a JSONL event log at an arbitrary path. Missing file -> []. Tolerant of a
    half-written trailing line (the tailer may catch the file mid-append)."""
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                # partial trailing line during a concurrent append — skip it
                continue
    return out


def read_events(mission_id: str) -> List[Dict[str, Any]]:
    """Read a mission's full event log as a list of dicts (see read_events_file)."""
    return read_events_file(events_path(mission_id))


REPLAYS_DIR = REPO_ROOT / "examples" / "replays"


def list_replays() -> List[tuple]:
    """Discover bundled replays on disk: every examples/replays/*.events.jsonl.
    Returns (id, abs_path) pairs (id = filename minus '.events.jsonl'), sorted by id.
    The catalog is the filesystem — drop a file in and it appears (CONTRACT §5.3)."""
    out: List[tuple] = []
    if REPLAYS_DIR.exists():
        for p in sorted(REPLAYS_DIR.glob("*.events.jsonl")):
            rid = p.name[: -len(".events.jsonl")]
            out.append((rid, p))
    return out


def ensure_sample_bundled() -> None:
    """Copy the reference 78-event replay into runs/ so the sample mission works OOTB
    (does not overwrite an existing log)."""
    dest = default_events_path("mission_fashion_sample")
    if dest.exists() or not SAMPLE_EVENTS.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(SAMPLE_EVENTS.read_text())
