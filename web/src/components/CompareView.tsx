// Node-view tab (compare): pick TWO experiment nodes and (a) diff their changes/configs
// side by side, (b) overlay their metric curves on ONE Recharts chart, (c) rank them on the
// objective metric with a signed delta. P1 DoD #2: "compare view ranks/overlays two nodes."
import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Experiment, MissionState } from "../types";
import { metricValue } from "../state/eventReducer";
import { STATUS_COLOR } from "../lib/status";
import { fmtMetric } from "../lib/utils";

const A_COLOR = "#38bdf8"; // sky
const B_COLOR = "#f59e0b"; // amber

function xOf(m: { epoch?: number; step?: number }, i: number): number {
  return m.epoch ?? m.step ?? i;
}

/** Merge two experiments' points for one metric into a single overlay dataset keyed by x. */
function overlayData(a: Experiment | undefined, b: Experiment | undefined, metricName: string) {
  const byX = new Map<number, { x: number; a?: number; b?: number }>();
  const add = (exp: Experiment | undefined, key: "a" | "b") => {
    if (!exp) return;
    exp.metrics
      .filter((m) => m.name === metricName)
      .forEach((m, i) => {
        const x = xOf(m, i);
        const row = byX.get(x) ?? { x };
        row[key] = m.value;
        byX.set(x, row);
      });
  };
  add(a, "a");
  add(b, "b");
  return [...byX.values()].sort((p, q) => p.x - q.x);
}

function NodePicker({
  label,
  color,
  value,
  options,
  onChange,
}: {
  label: string;
  color: string;
  value?: string;
  options: Experiment[];
  onChange: (id: string) => void;
}) {
  return (
    <label className="flex items-center gap-1.5 text-xs">
      <span
        className="inline-block h-2.5 w-2.5 rounded-full"
        style={{ backgroundColor: color }}
      />
      <span className="text-neutral-400">{label}</span>
      <select
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-neutral-700 bg-neutral-950 px-1.5 py-1 font-mono text-[11px] text-neutral-100 focus:border-sky-500 focus:outline-none"
      >
        <option value="" disabled>
          select node…
        </option>
        {options.map((e) => (
          <option key={e.id} value={e.id}>
            {e.id} · {e.operator ?? "—"} · {e.status}
          </option>
        ))}
      </select>
    </label>
  );
}

function ChangesDiff({ a, b }: { a?: Experiment; b?: Experiment }) {
  const ca = (a?.changes ?? {}) as Record<string, unknown>;
  const cb = (b?.changes ?? {}) as Record<string, unknown>;
  const keys = [...new Set([...Object.keys(ca), ...Object.keys(cb)])].sort();
  if (keys.length === 0)
    return (
      <div className="px-1 py-2 text-[11px] text-neutral-600">
        No config changes recorded for either node.
      </div>
    );
  const fmt = (v: unknown) => (v === undefined ? "—" : typeof v === "object" ? JSON.stringify(v) : String(v));
  return (
    <table className="w-full text-[11px]">
      <thead>
        <tr className="border-b border-neutral-800 text-left text-[10px] uppercase tracking-wide text-neutral-500">
          <th className="px-2 py-1">param</th>
          <th className="px-2 py-1" style={{ color: A_COLOR }}>
            {a?.id ?? "A"}
          </th>
          <th className="px-2 py-1" style={{ color: B_COLOR }}>
            {b?.id ?? "B"}
          </th>
        </tr>
      </thead>
      <tbody>
        {keys.map((k) => {
          const va = fmt(ca[k]);
          const vb = fmt(cb[k]);
          const differ = va !== vb;
          return (
            <tr key={k} className="border-b border-neutral-900">
              <td className="px-2 py-1 font-mono text-sky-300">{k}</td>
              <td className={`px-2 py-1 font-mono ${differ ? "text-amber-300" : "text-neutral-400"}`}>
                {va}
              </td>
              <td className={`px-2 py-1 font-mono ${differ ? "text-amber-300" : "text-neutral-400"}`}>
                {vb}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export function CompareView({
  state,
  selectedId,
  onSelect,
}: {
  state: MissionState;
  selectedId?: string;
  onSelect?: (id: string) => void;
}) {
  const metricName = state.mission?.objective?.metric ?? "val_accuracy";
  const direction = state.mission?.objective?.direction ?? "maximize";
  const experiments = state.experiments;

  const [aId, setAId] = useState<string | undefined>(selectedId);
  const [bId, setBId] = useState<string | undefined>();

  // Default A to the node-view selection; default B to a distinct sensible node.
  useEffect(() => {
    if (selectedId) setAId(selectedId);
  }, [selectedId]);
  useEffect(() => {
    if (bId || experiments.length === 0) return;
    const fallback =
      (state.bestExperimentId && state.bestExperimentId !== aId && state.bestExperimentId) ||
      experiments.map((e) => e.id).find((id) => id !== aId);
    if (fallback) setBId(fallback);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [experiments.length, aId]);

  const a = aId ? state.experimentsById[aId] : undefined;
  const b = bId ? state.experimentsById[bId] : undefined;

  const data = useMemo(() => overlayData(a, b, metricName), [a, b, metricName]);

  const va = a ? metricValue(a, metricName) : undefined;
  const vb = b ? metricValue(b, metricName) : undefined;

  // Rank + signed delta on the objective metric.
  let ranking: { winner?: "a" | "b" | "tie"; delta?: number } = {};
  if (va != null && vb != null) {
    if (va === vb) ranking = { winner: "tie", delta: 0 };
    else {
      const aBetter = direction === "maximize" ? va > vb : va < vb;
      ranking = { winner: aBetter ? "a" : "b", delta: Math.abs(va - vb) };
    }
  }

  if (experiments.length < 2)
    return (
      <div className="p-4 text-sm text-neutral-500">
        Need at least two nodes to compare. {experiments.length} so far.
      </div>
    );

  const WinnerCell = ({ exp, v, side }: { exp?: Experiment; v?: number; side: "a" | "b" }) => {
    const wins = ranking.winner === side;
    const color = side === "a" ? A_COLOR : B_COLOR;
    return (
      <button
        onClick={() => exp && onSelect?.(exp.id)}
        className={`flex-1 rounded-md border p-2 text-left transition-colors hover:bg-neutral-800/50 ${
          wins ? "border-amber-500/60 bg-amber-500/5" : "border-neutral-800"
        }`}
      >
        <div className="flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: color }} />
          <span className="font-mono text-xs" style={{ color: exp ? STATUS_COLOR[exp.status] : undefined }}>
            {exp?.id ?? "—"}
          </span>
          {wins && <span className="ml-auto text-[10px] font-bold text-amber-400">⭐ better</span>}
          {ranking.winner === "tie" && <span className="ml-auto text-[10px] text-neutral-500">tie</span>}
        </div>
        <div className="mt-1 font-mono text-lg text-neutral-100">{fmtMetric(v)}</div>
        <div className="text-[10px] text-neutral-500">{metricName}</div>
      </button>
    );
  };

  return (
    <div className="space-y-3 p-2">
      {/* pickers */}
      <div className="flex flex-wrap items-center gap-3">
        <NodePicker label="A" color={A_COLOR} value={aId} options={experiments} onChange={setAId} />
        <NodePicker label="B" color={B_COLOR} value={bId} options={experiments} onChange={setBId} />
      </div>

      {/* rank / delta */}
      <div className="flex items-stretch gap-2">
        <WinnerCell exp={a} v={va} side="a" />
        <div className="flex flex-col items-center justify-center px-1">
          <span className="text-[10px] uppercase text-neutral-500">Δ</span>
          <span className="font-mono text-sm text-amber-300">
            {ranking.delta != null ? fmtMetric(ranking.delta) : "—"}
          </span>
          <span className="text-[10px] text-neutral-600">{direction}</span>
        </div>
        <WinnerCell exp={b} v={vb} side="b" />
      </div>

      {/* overlaid metric curves */}
      <div>
        <div className="px-1 pb-1 text-[10px] uppercase tracking-wide text-neutral-500">
          {metricName} overlay
        </div>
        {data.length === 0 ? (
          <div className="px-1 py-3 text-[11px] text-neutral-600">
            No {metricName} points logged for the selected nodes.
          </div>
        ) : (
          <div className="h-44 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: -16 }}>
                <CartesianGrid stroke="#27272a" strokeDasharray="3 3" />
                <XAxis dataKey="x" stroke="#71717a" tick={{ fontSize: 11 }} />
                <YAxis stroke="#71717a" tick={{ fontSize: 11 }} domain={["auto", "auto"]} />
                <Tooltip
                  contentStyle={{
                    background: "#18181b",
                    border: "1px solid #3f3f46",
                    borderRadius: 6,
                    fontSize: 12,
                  }}
                  labelStyle={{ color: "#a1a1aa" }}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Line
                  type="monotone"
                  dataKey="a"
                  name={a?.id ?? "A"}
                  stroke={A_COLOR}
                  strokeWidth={2}
                  dot={{ r: 2, fill: A_COLOR }}
                  connectNulls
                  isAnimationActive={false}
                />
                <Line
                  type="monotone"
                  dataKey="b"
                  name={b?.id ?? "B"}
                  stroke={B_COLOR}
                  strokeWidth={2}
                  dot={{ r: 2, fill: B_COLOR }}
                  connectNulls
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* side-by-side config / changes diff */}
      <div>
        <div className="px-1 pb-1 text-[10px] uppercase tracking-wide text-neutral-500">
          config / changes diff
        </div>
        <div className="overflow-auto rounded-md border border-neutral-800">
          <ChangesDiff a={a} b={b} />
        </div>
      </div>
    </div>
  );
}
