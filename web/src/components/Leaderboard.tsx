// Node-view triad (3/3): results table of valid experiments sorted by the objective
// metric (default val_accuracy), best on top. Clicking a row selects that node.
import type { MissionState } from "../types";
import { metricValue } from "../state/eventReducer";
import { STATUS_COLOR } from "../lib/status";
import { fmtMetric } from "../lib/utils";

export function Leaderboard({
  state,
  selectedId,
  onSelect,
}: {
  state: MissionState;
  selectedId?: string;
  onSelect: (id: string) => void;
}) {
  const metricName = state.mission?.objective?.metric ?? "val_accuracy";
  const direction = state.mission?.objective?.direction ?? "maximize";

  // Valid (ran & produced a metric) experiments — exclude buggy/proposed/running.
  const rows = state.experiments
    .filter((e) => e.status === "valid" || e.status === "promoted")
    .map((e) => ({ exp: e, value: metricValue(e, metricName) }))
    .filter((r) => r.value != null)
    .sort((a, b) =>
      direction === "maximize" ? (b.value! - a.value!) : (a.value! - b.value!)
    );

  if (rows.length === 0)
    return <div className="p-4 text-sm text-neutral-500">No valid results yet.</div>;

  return (
    <div className="overflow-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-neutral-800 text-left text-[10px] uppercase tracking-wide text-neutral-500">
            <th className="px-3 py-2">#</th>
            <th className="px-3 py-2">Experiment</th>
            <th className="px-3 py-2">Op</th>
            <th className="px-3 py-2">Branch</th>
            <th className="px-3 py-2 text-right">{metricName}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const isBest = i === 0;
            const isSel = r.exp.id === selectedId;
            return (
              <tr
                key={r.exp.id}
                onClick={() => onSelect(r.exp.id)}
                className={`cursor-pointer border-b border-neutral-900 hover:bg-neutral-800/60 ${
                  isSel ? "bg-neutral-800" : ""
                }`}
              >
                <td className="px-3 py-1.5 font-mono text-neutral-500">
                  {isBest ? "⭐" : i + 1}
                </td>
                <td className="px-3 py-1.5 font-mono">
                  <span style={{ color: STATUS_COLOR[r.exp.status] }}>{r.exp.id}</span>
                </td>
                <td className="px-3 py-1.5 text-xs text-neutral-400">{r.exp.operator ?? "—"}</td>
                <td className="px-3 py-1.5 font-mono text-[11px] text-neutral-500">
                  {r.exp.branchId.replace("branch_", "")}
                </td>
                <td
                  className={`px-3 py-1.5 text-right font-mono ${
                    isBest ? "font-bold text-amber-400" : "text-neutral-200"
                  }`}
                >
                  {fmtMetric(r.value)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
