// Topbar instrument strip: mission name · mode pill · run-state (colored pulse) ·
// best metric (with ▲ delta vs previous best) · current experiment · budget
// progress bar (n/max) · elapsed runtime · driver model.
import type { Experiment, MissionState } from "../types";
import { fmtMetric } from "../lib/utils";
import { runStateColor, runStateLabel } from "../lib/status";

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col">
      <span className="text-[9px] uppercase tracking-wide text-neutral-500">{label}</span>
      <span className="text-sm font-semibold text-neutral-100">{children}</span>
    </div>
  );
}

/** Elapsed wall-clock between the first and last event. */
function elapsed(state: MissionState): string {
  const evs = state.events;
  if (evs.length < 2) return "—";
  const t0 = Date.parse(evs[0].timestamp);
  const t1 = Date.parse(evs[evs.length - 1].timestamp);
  if (Number.isNaN(t0) || Number.isNaN(t1)) return "—";
  const sec = Math.max(0, Math.round((t1 - t0) / 1000));
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  if (m < 60) return `${m}m ${s}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

/** Improvement of the current best over the previous best, walking experiments in
 *  order. Returns the absolute delta, or undefined if there was no prior best. */
function bestDelta(state: MissionState): number | undefined {
  const metricName = state.bestMetric?.name ?? state.mission?.objective?.metric;
  if (!metricName) return undefined;
  const minimize = state.mission?.objective?.direction === "minimize";
  const vals = state.experiments
    .map((e) => e.finalMetrics?.[metricName])
    .filter((v): v is number => typeof v === "number" && !Number.isNaN(v));
  if (vals.length < 2) return undefined;
  let best: number | undefined;
  let prevBest: number | undefined;
  for (const v of vals) {
    if (best === undefined) {
      best = v;
    } else if (minimize ? v < best : v > best) {
      prevBest = best;
      best = v;
    }
  }
  if (best === undefined || prevBest === undefined) return undefined;
  return Math.abs(best - prevBest);
}

function ModePill({ mode }: { mode: string }) {
  const color = mode.includes("live")
    ? "#34d399"
    : mode.includes("paused")
    ? "#f59e0b"
    : mode.includes("observe")
    ? "#a855f7"
    : "#38bdf8";
  return (
    <span
      className="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
      style={{ backgroundColor: `${color}22`, color, border: `1px solid ${color}55` }}
    >
      {mode}
    </span>
  );
}

export function TopbarStatus({
  state,
  selected,
  modeLabel,
  runState,
}: {
  state: MissionState;
  selected?: Experiment;
  modeLabel: string;
  /** Live Mode-A loop run_state from GET /state (CONTRACT §9.1). */
  runState?: "run" | "paused" | "stopped" | "finished";
}) {
  const m = state.mission;
  const best = state.bestMetric;
  const delta = bestDelta(state);
  const maxExp = m?.budget?.max_experiments;
  const used = state.budgetUsed;
  const pct = maxExp ? Math.min(100, Math.round((used / maxExp) * 100)) : undefined;
  const rsColor = runStateColor(runState);
  const running = runState === "run";

  return (
    <div className="flex items-center gap-5 border-b border-neutral-800 bg-neutral-950 px-4 py-2">
      <div className="flex min-w-0 flex-col">
        <span className="text-[9px] uppercase tracking-wide text-sky-500">Kun · Mission</span>
        <span className="max-w-[16rem] truncate text-base font-bold text-neutral-50">
          {m?.name ?? "—"}
        </span>
      </div>

      <ModePill mode={modeLabel} />

      {runState && (
        <div className="flex items-center gap-1.5">
          {running ? (
            <span className="relative flex h-2 w-2">
              <span
                className="absolute inline-flex h-full w-full animate-ping rounded-full opacity-60"
                style={{ backgroundColor: rsColor }}
              />
              <span
                className="relative inline-flex h-2 w-2 rounded-full"
                style={{ backgroundColor: rsColor }}
              />
            </span>
          ) : (
            <span className="h-2 w-2 rounded-full" style={{ backgroundColor: rsColor }} />
          )}
          <span className="text-xs font-semibold" style={{ color: rsColor }}>
            {runStateLabel(runState)}
          </span>
        </div>
      )}

      <div className="ml-1 h-8 w-px bg-neutral-800" />

      <Stat label="Best">
        <span className="text-amber-400">
          {best ? `${fmtMetric(best.value)} ` : "—"}
          {best && <span className="text-[10px] text-neutral-500">{best.name}</span>}
          {delta != null && delta > 0 && (
            <span className="ml-1 text-[10px] text-emerald-400">▲{fmtMetric(delta)}</span>
          )}
        </span>
      </Stat>

      <Stat label="Current">
        <span className="font-mono">{selected?.id ?? "—"}</span>
      </Stat>

      <Stat label="Budget">
        <div className="flex items-center gap-2">
          <span>
            {used}
            {maxExp ? <span className="text-neutral-500">/{maxExp}</span> : null}
          </span>
          {pct != null && (
            <div className="h-1.5 w-20 overflow-hidden rounded-full bg-neutral-800">
              <div
                className="h-full rounded-full bg-sky-500 transition-all"
                style={{ width: `${pct}%` }}
              />
            </div>
          )}
        </div>
      </Stat>

      <Stat label="Runtime">{elapsed(state)}</Stat>

      <Stat label="Driver model">
        <span className="font-mono text-xs">{m?.model ?? "—"}</span>
      </Stat>

      {state.finished && (
        <span className="ml-auto rounded bg-emerald-500/15 px-2 py-1 text-xs font-semibold text-emerald-400">
          mission complete · {state.finishReason}
        </span>
      )}
    </div>
  );
}
