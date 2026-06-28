#!/usr/bin/env python3
"""Tiny SSE smoke client for Kun's /missions/{id}/stream (CONTRACT §8.1 file-tail).

Connects, prints each event type as it arrives, and exits after --max events (or runs
until Ctrl-C). Use it to prove live tailing: start it, then append a line to
runs/<mission_id>/events.jsonl via kun_log and watch it show up here.

Usage:
  python scripts/smoke_sse.py mission_fashion_sample --max 80
  python scripts/smoke_sse.py mission_fashion_sample            # stream forever
"""
import argparse
import json
import sys
import urllib.request


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mission_id")
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--max", type=int, default=0, help="exit after N kun events (0 = forever)")
    args = ap.parse_args()

    url = f"{args.base}/missions/{args.mission_id}/stream"
    print(f"[smoke_sse] connecting to {url}", flush=True)
    req = urllib.request.Request(url, headers={"Accept": "text/event-stream"})

    count = 0
    cur_event = "message"
    with urllib.request.urlopen(req) as resp:  # noqa: S310 - local trusted URL
        for raw in resp:
            line = raw.decode("utf-8").rstrip("\n")
            if line.startswith("event:"):
                cur_event = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data = line[len("data:"):].strip()
                if cur_event == "ready":
                    info = json.loads(data)
                    print(f"[smoke_sse] >>> READY (backfill replayed {info['replayed']}) — now LIVE", flush=True)
                    continue
                try:
                    ev = json.loads(data)
                    etype = ev.get("type")
                    eid = ev.get("experiment_id") or ""
                    print(f"[smoke_sse] {count:>3} {etype} {eid}".rstrip(), flush=True)
                except json.JSONDecodeError:
                    print(f"[smoke_sse] {count:>3} <raw> {data}", flush=True)
                count += 1
                if args.max and count >= args.max:
                    print(f"[smoke_sse] reached --max {args.max}, exiting", flush=True)
                    return 0
            # blank line = end of one SSE message
    return 0


if __name__ == "__main__":
    sys.exit(main())
