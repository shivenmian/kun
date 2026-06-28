// The trajectory graph (React Flow). One node per experiment; edges parent->child.
// Nodes are BADGED by operator and COLORED by status (buggy = RED). The human fork
// branch reads as a visible, distinctly-styled branch off its parent node.
import { useMemo } from "react";
import ReactFlow, {
  Background,
  Controls,
  Handle,
  Position,
  type Edge,
  type Node,
  type NodeProps,
} from "reactflow";
import "reactflow/dist/style.css";
import type { Experiment, MissionState } from "../types";
import { OPERATOR_COLOR, STATUS_COLOR } from "../lib/status";
import { metricValue } from "../state/eventReducer";
import { fmtMetric } from "../lib/utils";

interface NodeData {
  exp: Experiment;
  metricName: string;
  selected: boolean;
  isBest: boolean;
}

function ExperimentNode({ data }: NodeProps<NodeData>) {
  const { exp, metricName, selected, isBest } = data;
  const color = STATUS_COLOR[exp.status];
  const opColor = exp.operator ? OPERATOR_COLOR[exp.operator] : "#64748b";
  const val = metricValue(exp, metricName);
  return (
    <div
      className="rounded-lg border-2 bg-neutral-900 px-3 py-2 text-left shadow-md"
      style={{
        borderColor: color,
        boxShadow: selected
          ? `0 0 0 3px ${color}aa`
          : isBest
          ? "0 0 0 2px #eab308aa"
          : undefined,
        minWidth: 150,
      }}
    >
      <Handle type="target" position={Position.Top} className="!bg-neutral-600" />
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-xs font-bold text-neutral-100">{exp.id}</span>
        {exp.operator && (
          <span
            className="rounded px-1 py-0.5 text-[9px] font-bold uppercase"
            style={{ backgroundColor: `${opColor}33`, color: opColor }}
          >
            {exp.operator}
          </span>
        )}
      </div>
      <div className="mt-1 flex items-center gap-1.5">
        <span
          className="inline-block h-2 w-2 rounded-full"
          style={{ backgroundColor: color }}
        />
        <span className="text-[10px] uppercase tracking-wide" style={{ color }}>
          {exp.status}
        </span>
        {isBest && <span className="text-[10px]">⭐</span>}
      </div>
      <div className="mt-1 font-mono text-[11px] text-neutral-300">
        {metricName}: {exp.status === "buggy" ? "NaN" : fmtMetric(val)}
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-neutral-600" />
    </div>
  );
}

const nodeTypes = { experiment: ExperimentNode };

/** Tidy tree layout: y by generation depth, x by recursive subtree centering. */
function computeLayout(experiments: Experiment[]): Record<string, { x: number; y: number }> {
  const byId = new Map(experiments.map((e) => [e.id, e]));
  const children = new Map<string, string[]>();
  const roots: string[] = [];
  for (const e of experiments) {
    if (e.parentId && byId.has(e.parentId)) {
      const arr = children.get(e.parentId) ?? [];
      arr.push(e.id);
      children.set(e.parentId, arr);
    } else {
      roots.push(e.id);
    }
  }
  // keep deterministic ordering (exp_006 before exp_007 etc.)
  for (const arr of children.values()) arr.sort();
  roots.sort();

  const pos: Record<string, { x: number; y: number }> = {};
  let nextX = 0;
  const X_GAP = 210;
  const Y_GAP = 130;
  const place = (id: string, depth: number): number => {
    const kids = children.get(id) ?? [];
    let x: number;
    if (kids.length === 0) {
      x = nextX;
      nextX += 1;
    } else {
      const xs = kids.map((k) => place(k, depth + 1));
      x = (Math.min(...xs) + Math.max(...xs)) / 2;
    }
    pos[id] = { x: x * X_GAP, y: depth * Y_GAP };
    return x;
  };
  for (const r of roots) place(r, 0);
  return pos;
}

export function TrajectoryGraph({
  state,
  selectedId,
  onSelect,
}: {
  state: MissionState;
  selectedId?: string;
  onSelect: (id: string) => void;
}) {
  const metricName = state.mission?.objective?.metric ?? "val_accuracy";

  const { nodes, edges } = useMemo(() => {
    const layout = computeLayout(state.experiments);
    const nodes: Node<NodeData>[] = state.experiments.map((exp) => ({
      id: exp.id,
      type: "experiment",
      position: layout[exp.id] ?? { x: 0, y: 0 },
      data: {
        exp,
        metricName,
        selected: exp.id === selectedId,
        isBest: exp.id === state.bestExperimentId,
      },
    }));

    const byId = new Map(state.experiments.map((e) => [e.id, e]));
    const edges: Edge[] = [];
    for (const exp of state.experiments) {
      if (!exp.parentId || !byId.has(exp.parentId)) continue;
      const parent = byId.get(exp.parentId)!;
      const isFork = parent.branchId !== exp.branchId; // crosses branches => fork edge
      edges.push({
        id: `${exp.parentId}->${exp.id}`,
        source: exp.parentId,
        target: exp.id,
        animated: isFork,
        style: isFork
          ? { stroke: "#a855f7", strokeWidth: 2.5, strokeDasharray: "6 4" }
          : { stroke: "#52525b", strokeWidth: 1.5 },
        label: isFork ? "fork" : undefined,
        labelStyle: { fill: "#a855f7", fontSize: 10, fontWeight: 700 },
        labelBgStyle: { fill: "#1c1917" },
      });
    }
    return { nodes, edges };
  }, [state.experiments, selectedId, state.bestExperimentId, metricName]);

  return (
    <div className="h-full w-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodeClick={(_, n) => onSelect(n.id)}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.2}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#27272a" gap={20} />
        <Controls className="!bg-neutral-800 !border-neutral-700" />
      </ReactFlow>
    </div>
  );
}
