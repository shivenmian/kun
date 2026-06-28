// Data-source abstraction. Everything funnels into the SAME reducer (eventReducer.ts).
// Two source kinds:
//   - "replay"  : load a static JSONL file (the sample), no backend needed.
//   - "live"    : hydrate from the backend, then subscribe to SSE for appended events.
//
// The backend HTTP surface is CONTRACT §5; all paths are prefixed with /api so the
// Vite dev proxy forwards them to http://localhost:8000 (see vite.config.ts).

import type { KunEvent } from "../types";
import { parseJsonl } from "../state/eventReducer";

export const API_BASE = "/api";

export interface EventSink {
  onBatch: (events: KunEvent[]) => void; // initial hydrate (ordered)
  onAppend: (event: KunEvent) => void; // live appended event
  onError?: (err: string) => void;
  onOpen?: () => void;
}

export interface DataSource {
  /** Begin streaming into the sink. Returns a disposer. */
  start: (sink: EventSink) => () => void;
  label: string;
}

/** Static replay of a bundled JSONL asset (default: /sample.events.jsonl). */
export function replaySource(url = "/sample.events.jsonl"): DataSource {
  return {
    label: "replay",
    start(sink) {
      let cancelled = false;
      fetch(url)
        .then((r) => {
          if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
          return r.text();
        })
        .then((text) => {
          if (cancelled) return;
          const events = parseJsonl(text);
          sink.onBatch(events);
          sink.onOpen?.();
        })
        .catch((e) => sink.onError?.(`Failed to load replay: ${String(e)}`));
      return () => {
        cancelled = true;
      };
    },
  };
}

/** Live mission: hydrate via /events then tail via SSE /stream (CONTRACT §5). */
export function liveSource(missionId: string): DataSource {
  return {
    label: `live:${missionId}`,
    start(sink) {
      let es: EventSource | null = null;
      let cancelled = false;
      const seen = new Set<string>();

      // 1) hydrate full history
      fetch(`${API_BASE}/missions/${missionId}/events`)
        .then((r) => (r.ok ? r.text() : Promise.reject(new Error(`${r.status}`))))
        .then((text) => {
          if (cancelled) return;
          // backend may return JSONL or a JSON array — handle both
          let events: KunEvent[] = [];
          const trimmed = text.trim();
          if (trimmed.startsWith("[")) {
            try {
              events = JSON.parse(trimmed) as KunEvent[];
            } catch {
              events = parseJsonl(text);
            }
          } else {
            events = parseJsonl(text);
          }
          for (const e of events) seen.add(e.event_id);
          sink.onBatch(events);
        })
        .catch((e) => sink.onError?.(`hydrate failed: ${String(e)}`))
        .finally(() => {
          if (cancelled) return;
          // 2) live tail
          es = new EventSource(`${API_BASE}/missions/${missionId}/stream`);
          es.onopen = () => sink.onOpen?.();
          es.onmessage = (m) => {
            try {
              const evt = JSON.parse(m.data) as KunEvent;
              if (evt.event_id && seen.has(evt.event_id)) return;
              if (evt.event_id) seen.add(evt.event_id);
              sink.onAppend(evt);
            } catch {
              /* ignore unparseable SSE frame */
            }
          };
          es.onerror = () => sink.onError?.("SSE connection error");
        });

      return () => {
        cancelled = true;
        es?.close();
      };
    },
  };
}

// ---- Action endpoints (CONTRACT §5) ----

export async function forkMission(
  missionId: string,
  body: { parent_experiment_id: string; instruction: string; constraint?: unknown }
): Promise<Response> {
  return fetch(`${API_BASE}/missions/${missionId}/fork`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

/** Observe an external mission (CONTRACT §8.2): register then it streams via /stream. */
export async function registerMission(missionId: string, eventsPath?: string): Promise<Response> {
  return fetch(`${API_BASE}/missions/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mission_id: missionId, events_path: eventsPath }),
  });
}

export async function createMission(payload: Record<string, unknown>): Promise<Response> {
  return fetch(`${API_BASE}/missions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function startMission(missionId: string): Promise<Response> {
  return fetch(`${API_BASE}/missions/${missionId}/start`, { method: "POST" });
}
