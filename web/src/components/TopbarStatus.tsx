// Topbar: mission name · best metric · current experiment · budget used (n/max) ·
// mode (A-live / replay / paused) · runtime · model.
import type { Experiment, MissionState } from "../types";
import { fmtMetric } from "../lib/utils";

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col">
      <span className="text-[9px] uppercase tracking-wide text-neutral-500">{label}</span>
      <span className="text-sm font-semibold text-neutral-100">{children}</span>
    </div>
  );
}

function runtimeFromEvents(state: MissionState): string {
  const evs = state.events;
  if (evs.length < 2) return "—";
  const t0 = Date.parse(evs[0].timestamp);
  const t1 = Date.parse(evs[evs.length - 1].timestamp);
  if (Number.isNaN(t0) || Number.isNaN(t1)) return "—";
  const sec = Math.max(0, Math.round((t1 - t0) / 1000));
  return `${sec}s`;
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
  const maxExp = m?.budget?.max_experiments;
  return (
    <div className="flex items-center gap-6 border-b border-neutral-800 bg-neutral-950 px-4 py-2">
      <div className="flex flex-col">
        <span className="text-[9px] uppercase tracking-wide text-sky-500">Kun · Mission</span>
        <span className="text-base font-bold text-neutral-50">{m?.name ?? "—"}</span>
      </div>
      <div className="ml-2 h-8 w-px bg-neutral-800" />
      <Stat label="Best">
        <span className="text-amber-400">
          {best ? `${fmtMetric(best.value)} ` : "—"}
          {best && <span className="text-[10px] text-neutral-500">{best.name}</span>}
        </span>
      </Stat>
      <Stat label="Current">
        <span className="font-mono">{selected?.id ?? "—"}</span>
      </Stat>
      <Stat label="Budget">
        {state.budgetUsed}
        {maxExp ? <span className="text-neutral-500">/{maxExp}</span> : null}
      </Stat>
      <Stat label="Mode">
        <span
          className={
            modeLabel.includes("live")
              ? "text-emerald-400"
              : modeLabel.includes("paused")
              ? "text-amber-400"
              : "text-sky-400"
          }
        >
          {modeLabel}
        </span>
      </Stat>
      {runState && (
        <Stat label="Run">
          <span
            className={
              runState === "run"
                ? "text-emerald-400"
                : runState === "paused"
                ? "text-amber-400"
                : "text-neutral-400"
            }
          >
            {runState}
          </span>
        </Stat>
      )}
      <Stat label="Runtime">{runtimeFromEvents(state)}</Stat>
      <Stat label="Model">
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
