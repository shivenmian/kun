// Recharts line chart of the selected node's metric points (val_accuracy over step/epoch).
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Experiment } from "../types";

export function MetricsChart({ exp, metricName = "val_accuracy" }: { exp?: Experiment; metricName?: string }) {
  if (!exp) return <div className="p-4 text-sm text-neutral-500">Select a node.</div>;
  const pts = exp.metrics.filter((m) => m.name === metricName);
  if (pts.length === 0)
    return <div className="p-4 text-sm text-neutral-500">No {metricName} points logged.</div>;

  const data = pts.map((m) => ({
    x: m.epoch ?? m.step ?? 0,
    value: m.value,
  }));

  return (
    <div className="h-44 w-full p-2">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: -16 }}>
          <CartesianGrid stroke="#27272a" strokeDasharray="3 3" />
          <XAxis
            dataKey="x"
            stroke="#71717a"
            tick={{ fontSize: 11 }}
            label={{ value: "epoch", position: "insideBottom", offset: -2, fontSize: 10, fill: "#71717a" }}
          />
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
          <Line
            type="monotone"
            dataKey="value"
            name={metricName}
            stroke="#38bdf8"
            strokeWidth={2}
            dot={{ r: 3, fill: "#38bdf8" }}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
