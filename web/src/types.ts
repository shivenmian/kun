// Kun event + materialized-state types. Mirrors CONTRACT.md §1–§4.
// Keep these aligned with W1's backend Pydantic models / state builder.

export type Actor =
  | { type: "agent"; name: string; model?: string }
  | { type: "human"; name: string };

/** Raw event envelope — every event (CONTRACT §1). */
export interface KunEvent {
  schema_version: number;
  event_id: string;
  timestamp: string; // ISO-8601 UTC
  type: string; // P0 types in CONTRACT §2; unknown types are ignored by the reducer
  mission_id: string;
  experiment_id?: string | null;
  branch_id?: string | null;
  parent_experiment_id?: string | null;
  actor?: Actor;
  payload: Record<string, unknown>;
}

export type Operator = "draft" | "debug" | "improve";

export type ExperimentStatus =
  | "proposed"
  | "running"
  | "valid"
  | "buggy"
  | "promoted"
  | "rejected"
  | "forked";

export interface MetricPoint {
  name: string;
  value: number;
  step?: number;
  epoch?: number;
  phase?: string;
}

/** Materialized experiment (one trajectory node) — CONTRACT §4. */
export interface Experiment {
  id: string;
  parentId?: string;
  branchId: string;
  operator?: Operator;
  status: ExperimentStatus;
  hypothesis?: string;
  rationale?: string;
  changes?: Record<string, unknown>;
  diff?: string;
  command?: string;
  metrics: MetricPoint[];
  finalMetrics?: Record<string, number>;
  verdict?: string;
  evidence?: string[];
  concerns?: string[];
  failureType?: string; // raw failure_type (e.g. nan_detected) for buggy nodes
  failureMessage?: string;
}

/** Canonical constraint object — CONTRACT §3. */
export interface Constraint {
  constraint_id: string;
  source: "human" | "learned";
  text: string;
  applies_to?: string[];
  bound?: { param: string; op: string; value: number };
  confidence?: string; // learned only
  supporting_experiments?: string[]; // learned only
  // derived
  priorConfidence?: string; // set by the reducer when a re-emitted constraint sharpens (e.g. medium->high)
  experimentId?: string; // where it landed (envelope experiment_id)
  branchId?: string;
  timestamp?: string;
}

export interface Branch {
  id: string;
  name?: string;
  source?: string;
  reason?: string;
  parentExperimentId?: string;
}

export interface Mission {
  id: string;
  name?: string;
  goal?: string;
  objective?: { metric: string; direction: "maximize" | "minimize"; target?: number };
  budget?: { max_experiments?: number; max_runtime_per_experiment_sec?: number };
  adapter?: string;
  model?: string;
  editableFiles?: string[];
  allowedChanges?: string[];
}

export type MissionMode = "live" | "replay" | "paused";

/** Materialized mission state produced by the reducer. */
export interface MissionState {
  mission?: Mission;
  experiments: Experiment[];
  experimentsById: Record<string, Experiment>;
  constraints: Constraint[];
  branches: Branch[];
  mode: MissionMode;
  bestExperimentId?: string;
  bestMetric?: { name: string; value: number };
  budgetUsed: number; // count of started/finished experiments
  finished: boolean;
  finishReason?: string;
  startedBy?: string;
  events: KunEvent[]; // raw stream, in order, for the event panel
}
