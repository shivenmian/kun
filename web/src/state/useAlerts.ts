// Lightweight, render-cheap alert/toast derivation. NO new endpoints — alerts are
// derived ONLY from the events already flowing through the reducer + the runtime
// snapshot (GET /state). The Mode-A loop runs ~5s/experiment, so the operator needs
// these so they never miss a steering window (NaN → constraint, approval needed,
// finished, new best).
//
// De-dupe strategy: we never re-toast the same event. Because App replaces the whole
// events array on hydrate/mission-switch (a "batch") but appends one event at a time
// while live, we distinguish the two by CONTENT (is `next` an append-extension of the
// previous array?). A batch/replace only PRIMES the seen-set (no toast); an append
// toasts only the freshly appended tail. This is robust to React coalescing and to the
// transient empty render between mission switches.
import { useEffect, useMemo, useRef, useState } from "react";
import type { KunEvent } from "../types";
import type { PendingApproval } from "../lib/api";

export type AlertTone = "info" | "warn" | "danger" | "success";

export interface Alert {
  id: string; // event_id (or `approval:<exp>`); used as React key + de-dupe key
  tone: AlertTone;
  title: string;
  detail?: string;
  sticky?: boolean; // sticky = stays until resolved (approval); else auto-dismiss
}

/** Map a single live event to an alert, or null if it isn't noteworthy. */
function alertForEvent(e: KunEvent): Alert | null {
  const p = (e.payload ?? {}) as Record<string, unknown>;
  switch (e.type) {
    case "experiment_failed": {
      const ft = (p.failure_type as string | undefined) ?? "";
      const where = e.experiment_id ?? "experiment";
      const isNan = ft.toLowerCase().includes("nan");
      return {
        id: e.event_id,
        tone: "danger",
        title: isNan ? `🛑 NaN detected on ${where}` : `🛑 ${where} failed`,
        detail: (p.message as string | undefined) ?? (ft || undefined),
      };
    }
    case "constraint_learned": {
      const text = (p.text as string | undefined) ?? (p.constraint_id as string | undefined);
      return {
        id: e.event_id,
        tone: "warn",
        title: "🛑 NaN → learned constraint",
        detail: text,
      };
    }
    case "decision_created": {
      if (p.decision !== "promote") return null;
      return {
        id: e.event_id,
        tone: "success",
        title: "▲ New best — promoted",
        detail: e.experiment_id ?? undefined,
      };
    }
    case "mission_finished": {
      const bm = p.best_metric as { name?: string; value?: number } | undefined;
      const detail =
        bm && bm.value != null
          ? `best ${bm.name ?? ""} ${bm.value}`.trim()
          : (p.reason as string | undefined);
      return {
        id: e.event_id,
        tone: "success",
        title: "✅ Mission finished",
        detail,
      };
    }
    default:
      return null;
  }
}

export function useAlerts(
  events: KunEvent[],
  pendingApproval: PendingApproval | null,
  enabled: boolean
): { alerts: Alert[]; dismiss: (id: string) => void; attentionCount: number } {
  const [eventAlerts, setEventAlerts] = useState<Alert[]>([]);
  const prevEvents = useRef<KunEvent[]>([]);
  const seen = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (!enabled) {
      prevEvents.current = [];
      seen.current.clear();
      setEventAlerts([]);
      return;
    }

    const prev = prevEvents.current;
    const next = events;
    prevEvents.current = next;

    // Reset on an emptied stream (mission switch / source change).
    if (next.length === 0) {
      seen.current.clear();
      setEventAlerts([]);
      return;
    }

    // Is `next` exactly `prev` plus an appended tail? (prev must be non-empty.)
    let isAppend = prev.length > 0 && next.length >= prev.length;
    if (isAppend) {
      for (let i = 0; i < prev.length; i++) {
        if (prev[i].event_id !== next[i].event_id) {
          isAppend = false;
          break;
        }
      }
    }

    if (!isAppend) {
      // Hydrate / replace → PRIME only (mark everything seen, no toast). Drop any
      // toasts from a previously-loaded mission.
      seen.current = new Set(next.map((e) => e.event_id));
      setEventAlerts([]);
      return;
    }

    // Live appended tail → toast the matching, not-yet-seen events.
    const fresh: Alert[] = [];
    for (let i = prev.length; i < next.length; i++) {
      const e = next[i];
      if (seen.current.has(e.event_id)) continue;
      seen.current.add(e.event_id);
      const a = alertForEvent(e);
      if (a) fresh.push(a);
    }
    if (fresh.length) setEventAlerts((p) => [...p, ...fresh]);
  }, [events, enabled]);

  // The approval alert is DERIVED (not stored): it appears while an approval is
  // pending and auto-clears the instant the backend resolves it. Sticky on purpose.
  const approvalAlert = useMemo<Alert | null>(() => {
    if (!enabled || !pendingApproval) return null;
    return {
      id: `approval:${pendingApproval.experiment_id}`,
      tone: "warn",
      sticky: true,
      title: `⚠ Approval needed on ${pendingApproval.experiment_id}`,
      detail: pendingApproval.hypothesis ?? pendingApproval.operator,
    };
  }, [enabled, pendingApproval]);

  const alerts = useMemo(
    () => (approvalAlert ? [...eventAlerts, approvalAlert] : eventAlerts),
    [eventAlerts, approvalAlert]
  );

  const dismiss = (id: string) => setEventAlerts((p) => p.filter((a) => a.id !== id));

  // Attention = this mission currently needs a human (an armed, pending approval).
  const attentionCount = approvalAlert ? 1 : 0;

  return { alerts, dismiss, attentionCount };
}
