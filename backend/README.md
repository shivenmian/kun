# Kun backend (W1 — API + event log + state)

FastAPI app over a JSONL event log with an in-memory state builder. **No SQLite, no DB**
(CONTRACT §7). One live mechanism: the backend **file-tails** `runs/<mission_id>/events.jsonl`
and pushes appended lines over SSE (CONTRACT §8.1).

## Run

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # pulls torch (W3); core API deps are enough to run
uvicorn app.main:app --port 8000         # works from backend/ OR repo root
```

Paths (`runs/`, `examples/`, `kun/`) resolve against the repo root regardless of CWD.
On startup the reference 78-event replay is copied to `runs/mission_fashion_sample/events.jsonl`
(only if missing) so `GET /missions/mission_fashion_sample/*` works out of the box.

CORS is open to the Vite dev origin (`http://localhost:5173`) and any `localhost`/`127.0.0.1` port.

## Endpoints (CONTRACT §5 + §8.2 — path names are FROZEN)

| Method | Path | Behavior |
|---|---|---|
| `GET`  | `/health` | Liveness probe. |
| `GET`  | `/missions` | `{ "missions": [ids…] }` — every `runs/<id>/events.jsonl` + registered ids. |
| `POST` | `/missions` | Body = `mission_created` payload (optional `mission_id`). Emits `mission_created`, returns `{mission_id}`. |
| `POST` | `/missions/{id}/start` | Body `{mode, started_by}`. Emits `mission_started`, then best-effort launches the W3 loop (see seam). |
| `GET`  | `/missions/{id}/events` | Full event log as a JSON array (replay/reload). |
| `GET`  | `/missions/{id}/experiments` | Materialized state (`build_state`) for initial hydrate. |
| `GET`  | `/missions/{id}/stream` | **SSE.** Replays all existing events, emits an `event: ready` marker, then file-tails for new lines (~250ms poll). The live channel for Mode A and Mode B. |
| `POST` | `/missions/{id}/fork` | Record-only (P0). Emits `fork_created` + `branch_created` (+ `constraint_added` if `constraint` in body). Returns `{mission_id, branch_id}`. |
| `POST` | `/missions/register` | Body `{mission_id, events_path?}`. Registers an externally-produced mission (default path `runs/<id>/events.jsonl`) so state hydrates from it and `/stream` tails it. |

Not built (out of P0 scope per CONTRACT): `POST /ingest`, `GET /state`.

## SSE format

Each event is an SSE message with `event: kun` and `data: <event JSON>`. After the historical
backfill the server sends `event: ready` `data: {"replayed": N}` so a client can flip to "live".

Smoke client: `python scripts/smoke_sse.py <mission_id> [--max N]`.

## Loop seam (for W3 / integration)

`POST /missions/{id}/start` calls `app.api.loop_hook.start_loop(mission_id, mode)`:

1. **In-process (preferred):** W3/lead calls `app.api.register_loop_runner(fn)` where
   `fn(mission_id, mode)` launches the loop. The loop writes events via `kun_log`
   (CONTRACT §6) — never by importing the API.
2. **Subprocess fallback:** if no runner is registered but `backend/app/loop/run_mission.py`
   exists, it's spawned as `python -m app.loop.run_mission <mission_id> <mode>`.
3. Otherwise `{"loop": "not_available"}` — the server still records `mission_started`.

All paths are guarded; the server runs fine before W3 lands.

## Layout (W1-owned)

- `app/events/` — Pydantic envelope/request models + `kun_log`-backed append/read I/O.
- `app/state/` — `build_state(events) -> dict` (pure; tolerant of unknown event types).
- `app/api/` — routes + the loop hook seam.
- `app/main.py` — app factory, CORS, startup sample bundling.
