"""kun_log — the entire contract surface an external loop needs (spec 00 §3).

Append a Kun trajectory event to $KUN_EVENTS (default: events.jsonl). The helper
auto-fills event_id, timestamp, and schema_version so a producer needs to know
nothing about Kun internals. See docs/03-event-schema.md for event types.
"""
import json
import os
import time
import uuid


def kun_log(event_type, payload, **envelope):
    # Optional `path=` overrides $KUN_EVENTS so the backend can append to a
    # specific per-mission log (runs/<mission_id>/events.jsonl). External
    # producers omit it and keep using $KUN_EVENTS — the ~5-line surface.
    path = envelope.pop("path", None) or os.environ.get("KUN_EVENTS", "events.jsonl")
    rec = {
        "schema_version": 1,
        "event_id": "evt_" + uuid.uuid4().hex[:12],
        "timestamp": envelope.pop(
            "timestamp", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        ),
        "type": event_type,
        "payload": payload,
        **envelope,
    }
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec
