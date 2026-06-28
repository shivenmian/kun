// Data-source abstraction. Everything funnels into the SAME reducer (eventReducer.ts).
// Two source kinds:
//   - "replay"  : load a static JSONL file (the sample), no backend needed.
//   - "live"    : hydrate from the backend, then subscribe to SSE for appended events.
//
// The backend HTTP surface is CONTRACT §5; all paths are prefixed with /api so the
// Vite dev proxy forwards them to http://localhost:8000 (see vite.config.ts).

import type { Constraint, KunEvent } from "../types";
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
          const handleFrame = (m: MessageEvent) => {
            try {
              const evt = JSON.parse(m.data) as KunEvent;
              if (evt.event_id && seen.has(evt.event_id)) return;
              if (evt.event_id) seen.add(evt.event_id);
              sink.onAppend(evt);
            } catch {
              /* ignore unparseable SSE frame (e.g. the "ready" marker) */
            }
          };
          // The backend tags appended events as `event: kun` (CONTRACT §5 stream),
          // which does NOT trigger es.onmessage — that only fires for unnamed
          // `message` frames. Listen for the named event AND keep onmessage as a
          // fallback so live tail works regardless of how the server names frames.
          es.addEventListener("kun", handleFrame as EventListener);
          es.onmessage = handleFrame;
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

// ---- P1 live-steering surface (CONTRACT §5.1 / §9) ----

/** Loop run-state as reported by GET /state (CONTRACT §9.1). */
export type RunState = "run" | "paused" | "stopped" | "finished";

/** The pending experiment awaiting human approval (CONTRACT §9.1 pending_approval). */
export interface PendingApproval {
  experiment_id: string;
  changes?: Record<string, unknown>;
  operator?: string;
  hypothesis?: string;
}

/** Feedback / hydrate object from GET /missions/{id}/state (CONTRACT §9.1).
 *  Kept tolerant: every field is optional so a partial backend shape never crashes the UI. */
export interface MissionRuntimeState {
  mission_id?: string;
  run_state?: RunState;
  approval_required?: boolean;
  active_constraints?: Constraint[];
  soft_lessons?: Constraint[];
  pending_approval?: PendingApproval | null;
  pending_instructions?: Array<{
    instruction_id: string;
    text: string;
    applies_from?: string;
    bound?: Record<string, unknown>;
  }>;
  pending_forks?: Array<{
    branch_id: string;
    parent_experiment_id?: string;
    instruction?: string;
    constraint?: unknown;
  }>;
  best?: { experiment_id: string; metric: { name: string; value: number } };
}

/** Pure read of the feedback channel. Returns null on any failure (endpoint may not
 *  exist yet — the API subagent lands it in parallel), so callers stay graceful. */
export async function getMissionState(missionId: string): Promise<MissionRuntimeState | null> {
  try {
    const r = await fetch(`${API_BASE}/missions/${missionId}/state`);
    if (!r.ok) return null;
    return (await r.json()) as MissionRuntimeState;
  } catch {
    return null;
  }
}

/** Inject mid-run guidance → emits instruction_added (CONTRACT §5.1 / §9.3). */
export async function instructMission(
  missionId: string,
  body: { text: string; applies_from?: string; bound?: Record<string, unknown> }
): Promise<Response> {
  return fetch(`${API_BASE}/missions/${missionId}/instruct`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

/** Approve a proposed experiment → emits experiment_approved (CONTRACT §5.1 / §9.3). */
export async function approveExperiment(
  missionId: string,
  experimentId: string,
  body: { edited?: boolean; changes?: Record<string, unknown>; note?: string } = {}
): Promise<Response> {
  return fetch(`${API_BASE}/missions/${missionId}/experiments/${experimentId}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

/** Reject a proposed experiment → emits experiment_rejected (CONTRACT §5.1 / §9.3). */
export async function rejectExperiment(
  missionId: string,
  experimentId: string,
  body: { reason: string; replacement_changes?: Record<string, unknown> }
): Promise<Response> {
  return fetch(`${API_BASE}/missions/${missionId}/experiments/${experimentId}/reject`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

/** Stop / pause / resume the Mode-A loop → writes control.json (CONTRACT §5.1 / §9.2). */
export async function controlMission(
  missionId: string,
  action: "stop" | "pause" | "resume",
  extra?: { approval_required?: boolean; reason?: string }
): Promise<Response> {
  return fetch(`${API_BASE}/missions/${missionId}/stop`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, ...extra }),
  });
}
