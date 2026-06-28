// Mission history — the rail's mission list. Renders every known mission as a
// compact, clickable row (CONTRACT §5.2 enriched GET /missions), grouped
// running → needs-attention → finished, each group kept in the backend's
// most-recently-updated order. Presentational: MissionNavigator owns the data
// fetch, the search filter and the rail chrome; this component just renders rows.
import type { MissionSummary, LaunchChoice } from "../lib/api";
import { Badge } from "./ui/primitives";
import { runStateColor, runStateLabel } from "../lib/status";
import { fmtMetric, relativeTime } from "../lib/utils";
import { cn } from "../lib/utils";

/** Decide how a row routes into the launch flow.
 *   - active live mission  → { kind:"live",    missionId }  (hydrate + SSE + steering)
 *   - finished / external  → { kind:"observe", missionId }  (register then SSE) */
export function routeFor(m: MissionSummary): LaunchChoice {
  const rs = m.run_state ?? "";
  const active = rs === "run" || rs === "running" || rs === "paused" || rs === "pause";
  if (m.mode === "live" && active) return { kind: "live", missionId: m.mission_id };
  return { kind: "observe", missionId: m.mission_id };
}

function isActive(m: MissionSummary): boolean {
  const rs = m.run_state ?? "";
  return rs === "run" || rs === "running" || rs === "paused" || rs === "pause";
}
function isRunning(m: MissionSummary): boolean {
  const rs = m.run_state ?? "";
  return rs === "run" || rs === "running";
}
function needsAttention(m: MissionSummary): boolean {
  return m.pending_approval === true;
}

type Group = { key: string; label: string; rows: MissionSummary[] };

function group(missions: MissionSummary[]): Group[] {
  const running: MissionSummary[] = [];
  const attention: MissionSummary[] = [];
  const finished: MissionSummary[] = [];
  for (const m of missions) {
    if (needsAttention(m)) attention.push(m);
    else if (isActive(m)) running.push(m);
    else finished.push(m);
  }
  return [
    { key: "running", label: "Running", rows: running },
    { key: "attention", label: "Needs attention", rows: attention },
    { key: "finished", label: "Finished", rows: finished },
  ].filter((g) => g.rows.length > 0);
}

function MissionRow({
  m,
  active,
  onOpen,
}: {
  m: MissionSummary;
  active: boolean;
  onOpen: (m: MissionSummary) => void;
}) {
  const best = m.best?.metric;
  const bestVal = typeof best?.value === "number" ? best.value : undefined;
  const running = isRunning(m);
  const attention = needsAttention(m);
  return (
    <button
      type="button"
      onClick={() => onOpen(m)}
      title={`Open ${m.mission_id}`}
      className={cn(
        "group flex w-full flex-col gap-1 rounded-md border px-2.5 py-2 text-left transition-colors",
        active
          ? "border-sky-600/70 bg-sky-950/40"
          : "border-transparent hover:border-neutral-800 hover:bg-neutral-800/50"
      )}
    >
      <div className="flex items-center gap-1.5">
        {running ? (
          <span className="relative flex h-2 w-2 flex-none">
            <span
              className="absolute inline-flex h-full w-full animate-ping rounded-full opacity-60"
              style={{ backgroundColor: runStateColor(m.run_state ?? undefined) }}
            />
            <span
              className="relative inline-flex h-2 w-2 rounded-full"
              style={{ backgroundColor: runStateColor(m.run_state ?? undefined) }}
            />
          </span>
        ) : (
          <span
            className="h-2 w-2 flex-none rounded-full"
            style={{ backgroundColor: runStateColor(m.run_state ?? undefined) }}
          />
        )}
        <span className="min-w-0 flex-1 truncate text-xs font-medium text-neutral-100">
          {m.name || m.mission_id}
        </span>
        {typeof m.experiments_count === "number" && (
          <span className="flex-none font-mono text-[10px] text-neutral-500">
            {m.experiments_count}exp
          </span>
        )}
      </div>

      <div className="flex items-center gap-1.5 pl-3.5">
        {m.run_state && (
          <Badge color={runStateColor(m.run_state)}>{runStateLabel(m.run_state)}</Badge>
        )}
        {attention && (
          <Badge color="#f59e0b" className="animate-pulse">
            ⚠ needs approval
          </Badge>
        )}
        {bestVal != null ? (
          <span className="font-mono text-[10px] text-amber-400">{fmtMetric(bestVal)}</span>
        ) : null}
        <span className="ml-auto flex-none text-[10px] text-neutral-600">
          {relativeTime(m.updated_at ?? undefined)}
        </span>
      </div>
    </button>
  );
}

export function MissionHistory({
  missions,
  activeId,
  onOpen,
  loading,
}: {
  missions: MissionSummary[];
  activeId?: string;
  onOpen: (m: MissionSummary) => void;
  loading: boolean;
}) {
  if (missions.length === 0) {
    return (
      <div className="px-2 py-6 text-center text-[11px] text-neutral-600">
        {loading ? "Loading missions…" : "No missions match."}
      </div>
    );
  }
  const groups = group(missions);
  return (
    <div className="flex flex-col gap-3">
      {groups.map((g) => (
        <div key={g.key}>
          <div className="mb-1 flex items-center gap-1.5 px-1 text-[9px] uppercase tracking-wide text-neutral-600">
            {g.label}
            <span className="text-neutral-700">·</span>
            <span>{g.rows.length}</span>
          </div>
          <div className="flex flex-col gap-0.5">
            {g.rows.map((m) => (
              <MissionRow
                key={m.mission_id}
                m={m}
                active={m.mission_id === activeId}
                onOpen={onOpen}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
