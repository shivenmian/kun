// Live-tailing list of raw events (type + key fields + timestamp). Newest at bottom,
// auto-scrolls when new events arrive (live mode).
import { useEffect, useRef } from "react";
import type { KunEvent } from "../types";
import { shortTime } from "../lib/utils";

const TYPE_COLOR: Record<string, string> = {
  mission_created: "#a1a1aa",
  mission_started: "#a1a1aa",
  experiment_proposed: "#0ea5e9",
  file_diff_created: "#64748b",
  experiment_started: "#38bdf8",
  metric_logged: "#22d3ee",
  experiment_finished: "#22c55e",
  experiment_failed: "#ef4444",
  evaluation_created: "#eab308",
  decision_created: "#f59e0b",
  constraint_learned: "#ef4444",
  constraint_added: "#a855f7",
  fork_created: "#a855f7",
  branch_created: "#a855f7",
  mission_finished: "#22c55e",
};

function summarize(e: KunEvent): string {
  const p = e.payload ?? {};
  switch (e.type) {
    case "metric_logged":
      return `${p.name}=${p.value} @epoch ${p.epoch ?? p.step}`;
    case "experiment_proposed":
      return `${p.operator}: ${(p.hypothesis as string) ?? ""}`;
    case "experiment_finished":
      return `success ${JSON.stringify(p.final_metrics ?? {})}`;
    case "experiment_failed":
      return `${p.failure_type}: ${p.message}`;
    case "constraint_learned":
    case "constraint_added":
      return `${p.constraint_id}: ${p.text}`;
    case "decision_created":
      return `${p.decision}`;
    case "evaluation_created":
      return `${p.verdict}: ${p.summary ?? ""}`;
    case "fork_created":
      return `${p.instruction ?? ""}`;
    case "mission_finished":
      return `${p.reason} · best ${p.best_experiment_id}`;
    default:
      return "";
  }
}

export function EventStream({ events }: { events: KunEvent[] }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.scrollTo({ top: ref.current.scrollHeight });
  }, [events.length]);

  return (
    <div ref={ref} className="h-full overflow-auto px-2 py-1 font-mono text-[11px]">
      {events.map((e) => (
        <div key={e.event_id} className="flex items-start gap-2 border-b border-neutral-900 py-0.5">
          <span className="shrink-0 text-neutral-600">{shortTime(e.timestamp)}</span>
          <span
            className="shrink-0 font-semibold"
            style={{ color: TYPE_COLOR[e.type] ?? "#a1a1aa" }}
          >
            {e.type}
          </span>
          {e.experiment_id && <span className="shrink-0 text-neutral-500">{e.experiment_id}</span>}
          <span className="truncate text-neutral-400">{summarize(e)}</span>
        </div>
      ))}
    </div>
  );
}
