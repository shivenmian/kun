// Pure reducer: an ordered list of Kun events -> materialized MissionState.
// This is the single code path for BOTH static replay and live SSE (CONTRACT §8.1).
// It mirrors W1's backend state builder; keep them consistent with CONTRACT §4.
//
// Design rules:
//  - Pure & incremental: applyEvent(state, evt) folds one event; reduceEvents folds many.
//  - Tolerant of unknown event types: ignore, never throw (P1 events come later, CONTRACT §2).
//  - STATUS MAPPING lives in exactly one place: `mapStatus` below (CONTRACT §4).

import type {
  Constraint,
  Experiment,
  KunEvent,
  Mission,
  MissionState,
  MetricPoint,
  Operator,
} from "../types";

export function emptyState(): MissionState {
  return {
    mission: undefined,
    experiments: [],
    experimentsById: {},
    constraints: [],
    branches: [],
    mode: "replay",
    bestExperimentId: undefined,
    bestMetric: undefined,
    budgetUsed: 0,
    finished: false,
    events: [],
  };
}

// ---------------------------------------------------------------------------
// STATUS MAPPING (CONTRACT §4) — the ONLY place node-lifecycle status is set.
//   experiment_proposed         -> proposed
//   experiment_started          -> running
//   experiment_finished:success -> valid
//   experiment_failed           -> buggy
//   decision_created:promote    -> promoted
//   decision_created:reject     -> rejected
//   fork target / branch source -> forked (handled where forks are recorded)
// Raw payloads keep success/failed/nan_detected; valid/buggy is the cockpit vocabulary.
// ---------------------------------------------------------------------------
function mapStatusFromEvent(type: string, payload: Record<string, unknown>): Experiment["status"] | null {
  switch (type) {
    case "experiment_proposed":
      return "proposed";
    case "experiment_started":
      return "running";
    case "experiment_finished":
      return "valid"; // status:"success" per contract
    case "experiment_failed":
      return "buggy";
    case "decision_created": {
      const d = payload.decision as string | undefined;
      if (d === "promote") return "promoted";
      if (d === "reject") return "rejected";
      return null; // continue_branch / retry_debug / fork / stop don't change node color
    }
    default:
      return null;
  }
}

function ensureExperiment(state: MissionState, id: string, branchId?: string): Experiment {
  let exp = state.experimentsById[id];
  if (!exp) {
    exp = {
      id,
      branchId: branchId ?? "branch_main",
      status: "proposed",
      metrics: [],
    };
    state.experimentsById[id] = exp;
    state.experiments.push(exp);
  }
  return exp;
}

const STATUS_RANK: Record<Experiment["status"], number> = {
  proposed: 0,
  running: 1,
  valid: 2,
  forked: 2,
  rejected: 3,
  buggy: 3,
  promoted: 4,
};

/** Apply a single event, mutating a draft state. Returns the same state. */
export function applyEvent(state: MissionState, evt: KunEvent): MissionState {
  state.events.push(evt);
  const p = (evt.payload ?? {}) as Record<string, unknown>;
  const expId = evt.experiment_id ?? undefined;
  const branchId = evt.branch_id ?? undefined;

  switch (evt.type) {
    case "mission_created": {
      const mission: Mission = {
        id: evt.mission_id,
        name: p.name as string,
        goal: p.goal as string,
        objective: p.objective as Mission["objective"],
        budget: p.budget as Mission["budget"],
        adapter: p.adapter as string,
        model: p.model as string,
        editableFiles: p.editable_files as string[],
        allowedChanges: p.allowed_changes as string[],
      };
      state.mission = mission;
      // seed any human constraints declared at mission creation
      const seed = (p.constraints as Constraint[] | undefined) ?? [];
      for (const c of seed) addConstraint(state, c, undefined, undefined, evt.timestamp);
      // ensure main branch exists
      if (!state.branches.find((b) => b.id === "branch_main")) {
        state.branches.push({ id: "branch_main", name: "main" });
      }
      break;
    }

    case "mission_started": {
      const mode = p.mode as string | undefined;
      state.mode = mode === "replay" ? "replay" : "live";
      state.startedBy = p.started_by as string | undefined;
      break;
    }

    case "branch_created": {
      if (branchId && !state.branches.find((b) => b.id === branchId)) {
        state.branches.push({
          id: branchId,
          name: p.name as string,
          source: p.source as string,
          reason: p.reason as string,
          parentExperimentId: evt.parent_experiment_id ?? undefined,
        });
      }
      break;
    }

    case "fork_created": {
      // Record-only in P0. Mark the parent node as a fork point (forked status)
      // and register the new branch if not already created.
      if (branchId && !state.branches.find((b) => b.id === branchId)) {
        state.branches.push({
          id: branchId,
          name: (p.instruction as string)?.slice(0, 40),
          source: "human_fork",
          reason: p.reason as string,
          parentExperimentId: evt.parent_experiment_id ?? undefined,
        });
      }
      break;
    }

    case "constraint_added":
    case "constraint_learned": {
      const c = p as unknown as Constraint;
      addConstraint(state, c, expId, branchId, evt.timestamp);
      break;
    }

    case "experiment_proposed": {
      const exp = ensureExperiment(state, expId ?? `exp_${state.experiments.length}`, branchId);
      exp.operator = p.operator as Operator;
      exp.hypothesis = p.hypothesis as string;
      exp.rationale = p.rationale as string;
      exp.changes = p.changes as Record<string, unknown>;
      if (evt.parent_experiment_id) exp.parentId = evt.parent_experiment_id;
      setStatus(exp, "proposed");
      break;
    }

    case "file_diff_created": {
      if (expId) {
        const exp = ensureExperiment(state, expId, branchId);
        exp.diff = p.diff as string;
      }
      break;
    }

    case "experiment_started": {
      if (expId) {
        const exp = ensureExperiment(state, expId, branchId);
        exp.command = p.command as string;
        if (evt.parent_experiment_id) exp.parentId = evt.parent_experiment_id;
        setStatus(exp, "running");
        state.budgetUsed = countStarted(state);
      }
      break;
    }

    case "metric_logged": {
      if (expId) {
        const exp = ensureExperiment(state, expId, branchId);
        const mp: MetricPoint = {
          name: p.name as string,
          value: Number(p.value),
          step: p.step as number | undefined,
          epoch: p.epoch as number | undefined,
          phase: p.phase as string | undefined,
        };
        exp.metrics.push(mp);
      }
      break;
    }

    case "experiment_finished": {
      if (expId) {
        const exp = ensureExperiment(state, expId, branchId);
        exp.finalMetrics = p.final_metrics as Record<string, number>;
        setStatus(exp, "valid");
        recomputeBest(state);
      }
      break;
    }

    case "experiment_failed": {
      if (expId) {
        const exp = ensureExperiment(state, expId, branchId);
        exp.failureType = p.failure_type as string;
        exp.failureMessage = p.message as string;
        setStatus(exp, "buggy");
      }
      break;
    }

    case "evaluation_created": {
      if (expId) {
        const exp = ensureExperiment(state, expId, branchId);
        exp.verdict = p.verdict as string;
        exp.evidence = p.evidence as string[];
        exp.concerns = p.concerns as string[];
      }
      break;
    }

    case "decision_created": {
      if (expId) {
        const exp = ensureExperiment(state, expId, branchId);
        const mapped = mapStatusFromEvent(evt.type, p);
        if (mapped) setStatus(exp, mapped);
      }
      break;
    }

    case "mission_finished": {
      state.finished = true;
      state.finishReason = p.reason as string;
      const best = p.best_experiment_id as string | undefined;
      if (best) state.bestExperimentId = best;
      const bm = p.best_metric as { name: string; value: number } | undefined;
      if (bm) state.bestMetric = bm;
      break;
    }

    default:
      // Unknown / P1 event type — ignore, never crash (CONTRACT §2).
      break;
  }

  return state;
}

/** Only advance status forward (a later metric_logged shouldn't un-promote a node). */
function setStatus(exp: Experiment, next: Experiment["status"]) {
  // promote/reject/buggy are terminal-ish; allow them to override running/valid.
  if (next === "promoted" || next === "rejected" || next === "buggy") {
    exp.status = next;
    return;
  }
  if (STATUS_RANK[next] >= STATUS_RANK[exp.status]) exp.status = next;
}

function addConstraint(
  state: MissionState,
  c: Constraint,
  expId?: string,
  branchId?: string,
  timestamp?: string
) {
  if (!c || !c.constraint_id) return;
  if (state.constraints.find((x) => x.constraint_id === c.constraint_id)) return;
  state.constraints.push({ ...c, experimentId: expId, branchId, timestamp });
}

function countStarted(state: MissionState): number {
  // budget = number of distinct experiments that have actually started running.
  return state.experiments.filter(
    (e) => e.status !== "proposed"
  ).length;
}

/** Best valid/promoted node by the objective metric (default: maximize val_accuracy). */
function recomputeBest(state: MissionState) {
  const metricName = state.mission?.objective?.metric ?? "val_accuracy";
  const direction = state.mission?.objective?.direction ?? "maximize";
  let best: { id: string; value: number } | undefined;
  for (const e of state.experiments) {
    if (e.status === "buggy" || e.status === "rejected") continue;
    const v = metricValue(e, metricName);
    if (v == null) continue;
    if (!best) best = { id: e.id, value: v };
    else if (direction === "maximize" ? v > best.value : v < best.value) best = { id: e.id, value: v };
  }
  if (best) {
    state.bestExperimentId = best.id;
    state.bestMetric = { name: metricName, value: best.value };
  }
}

export function metricValue(exp: Experiment, metricName: string): number | undefined {
  if (exp.finalMetrics && exp.finalMetrics[metricName] != null) return exp.finalMetrics[metricName];
  const pts = exp.metrics.filter((m) => m.name === metricName);
  if (pts.length) return pts[pts.length - 1].value;
  return undefined;
}

/** Fold an ordered list of events into a fresh MissionState. */
export function reduceEvents(events: KunEvent[]): MissionState {
  const state = emptyState();
  for (const evt of events) applyEvent(state, evt);
  // mission_finished may have set best; otherwise compute it now.
  if (!state.bestExperimentId) recomputeBest(state);
  return state;
}

/** Parse a JSONL string (e.g. the sample replay) into events, skipping blanks. */
export function parseJsonl(text: string): KunEvent[] {
  const out: KunEvent[] = [];
  for (const line of text.split("\n")) {
    const t = line.trim();
    if (!t) continue;
    try {
      out.push(JSON.parse(t) as KunEvent);
    } catch {
      // skip malformed lines rather than crash the replay
    }
  }
  return out;
}
