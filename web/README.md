# Kun Cockpit (web)

Mission-control cockpit for autonomous ML research trajectories. Renders the Kun
event log (CONTRACT.md) as a forkable trajectory graph + node view + research-memory
panel, driven entirely by events. Live mode and static replay share **one reducer**
and **one code path** (`src/state/eventReducer.ts`).

## Run

```bash
cd web
npm install
npm run dev          # http://localhost:5173
npm run build        # typecheck (tsc -b) + production build
npm run preview      # serve the production build
```

The cockpit opens on a **mission launcher**. Three ways in:

1. **Load sample replay** — renders `public/sample.events.jsonl` (the 78-event
   reference trajectory) with **no backend running**. Works fully offline.
2. **Connect to live mission `{id}`** — hydrate via `/api/missions/{id}/events`,
   then tail `/api/missions/{id}/stream` (SSE).
3. **Observe external mission `{id}`** — `POST /api/missions/register`, then open its
   SSE stream (CONTRACT §8.2 wedge proof).

### Demo deep links

- `?replay` — auto-load the sample replay (used for screenshots/demos)
- `?live=<mission_id>` — auto-connect to a live mission
- `?observe=<mission_id>` — auto-register + observe an external mission

## Backend wiring

`vite.config.ts` proxies `/api/*` → `http://localhost:8000` (FastAPI, CONTRACT §5),
stripping the `/api` prefix. Endpoints consumed:

| Frontend call | Backend (CONTRACT §5) |
|---|---|
| `GET /api/missions/{id}/events` | full event log (JSONL or JSON array) — hydrate |
| `GET /api/missions/{id}/stream` | **SSE** — live append (EventSource) |
| `POST /api/missions/{id}/fork` | record a fork (P0 = record/visualize only) |
| `POST /api/missions/register` | register + tail an external mission log (§8.2) |
| `POST /api/missions`, `/start` | create / start a mission |

The static replay path does **not** use the proxy — it loads `/sample.events.jsonl`
straight from `public/`, so the core product visual works with no backend.

## Architecture

- `src/types.ts` — Kun event envelope + materialized `Experiment` / `Constraint` /
  `MissionState` (CONTRACT §1–§4).
- `src/state/eventReducer.ts` — **pure reducer**: `reduceEvents(events) -> MissionState`.
  The §4 **status mapping** lives in one place (`mapStatusFromEvent` + `setStatus`).
  Unknown / P1 event types are ignored (never crash).
- `src/lib/api.ts` — data-source abstraction (`replaySource`, `liveSource`) behind one
  `EventSink` interface; both feed the same reducer. Swapping mock → real backend is
  trivial.
- `src/lib/status.ts` — status colors (buggy = RED) + operator badge colors.
- `src/components/` — `TrajectoryGraph` (React Flow), node-view triad
  (`ExperimentDetails` / `DiffViewer` / `Leaderboard`), `MetricsChart` (Recharts),
  `ResearchMemoryPanel` (hero), `EventStream`, `TopbarStatus`, `ForkDialog`,
  `MissionLauncher`.

## Stack

Vite + React + TypeScript · Tailwind · React Flow · Recharts · react-diff-viewer
(`react-diff-viewer-continued`, the React 18-compatible maintained fork). UI
primitives are hand-rolled in the shadcn visual language (Tailwind only, no Radix)
to keep the build offline-safe.
