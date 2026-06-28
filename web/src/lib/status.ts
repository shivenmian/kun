import type { ExperimentStatus, Operator } from "../types";

// Colored by STATUS (CONTRACT §4: buggy = RED, promoted highlighted, proposed/running muted).
export const STATUS_COLOR: Record<ExperimentStatus, string> = {
  valid: "#22c55e", // green
  buggy: "#ef4444", // RED (NaN / failed)
  promoted: "#eab308", // highlighted gold
  running: "#38bdf8", // muted blue
  proposed: "#94a3b8", // muted gray
  rejected: "#f97316", // orange
  forked: "#a855f7", // purple
};

export const STATUS_LABEL: Record<ExperimentStatus, string> = {
  valid: "valid",
  buggy: "buggy",
  promoted: "promoted",
  running: "running",
  proposed: "proposed",
  rejected: "rejected",
  forked: "forked",
};

// Badged by OPERATOR (draft / debug / improve).
export const OPERATOR_COLOR: Record<Operator, string> = {
  draft: "#0ea5e9",
  debug: "#f59e0b",
  improve: "#10b981",
};

export function statusColor(s: ExperimentStatus): string {
  return STATUS_COLOR[s] ?? "#94a3b8";
}
