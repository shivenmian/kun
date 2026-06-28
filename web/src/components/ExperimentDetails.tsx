// Node-view triad (1/3): hypothesis / rationale / changes / verdict / evidence /
// concerns / command for the selected experiment.
import type { Experiment } from "../types";
import { STATUS_COLOR, OPERATOR_COLOR } from "../lib/status";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  if (children == null || children === "") return null;
  return (
    <div className="mb-3">
      <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-neutral-500">
        {label}
      </div>
      <div className="text-sm text-neutral-200">{children}</div>
    </div>
  );
}

export function ExperimentDetails({ exp }: { exp?: Experiment }) {
  if (!exp) {
    return <div className="p-4 text-sm text-neutral-500">Select a node to inspect it.</div>;
  }
  const color = STATUS_COLOR[exp.status];
  return (
    <div className="p-3">
      <div className="mb-3 flex items-center gap-2">
        <span className="font-mono text-base font-bold text-neutral-100">{exp.id}</span>
        {exp.operator && (
          <span
            className="rounded px-1.5 py-0.5 text-[10px] font-bold uppercase"
            style={{
              backgroundColor: `${OPERATOR_COLOR[exp.operator]}33`,
              color: OPERATOR_COLOR[exp.operator],
            }}
          >
            {exp.operator}
          </span>
        )}
        <span
          className="rounded px-1.5 py-0.5 text-[10px] font-bold uppercase"
          style={{ backgroundColor: `${color}22`, color }}
        >
          {exp.status}
        </span>
        <span className="ml-auto font-mono text-[10px] text-neutral-500">{exp.branchId}</span>
      </div>

      <Field label="Hypothesis">{exp.hypothesis}</Field>
      <Field label="Rationale">{exp.rationale}</Field>

      {exp.changes && Object.keys(exp.changes).length > 0 && (
        <Field label="Changes (vs parent)">
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(exp.changes).map(([k, v]) => (
              <span
                key={k}
                className="rounded bg-neutral-800 px-1.5 py-0.5 font-mono text-xs text-sky-300"
              >
                {k} = {JSON.stringify(v)}
              </span>
            ))}
          </div>
        </Field>
      )}

      {exp.verdict && (
        <Field label="Verdict">
          <span
            className="rounded px-1.5 py-0.5 text-xs font-semibold"
            style={{
              backgroundColor: exp.verdict === "promote" ? "#22c55e22" : "#f9731622",
              color: exp.verdict === "promote" ? "#22c55e" : "#f97316",
            }}
          >
            {exp.verdict}
          </span>
        </Field>
      )}

      {exp.evidence && exp.evidence.length > 0 && (
        <Field label="Evidence">
          <ul className="list-disc pl-4 text-sm text-neutral-300">
            {exp.evidence.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </Field>
      )}

      {exp.concerns && exp.concerns.length > 0 && (
        <Field label="Concerns">
          <ul className="list-disc pl-4 text-sm text-amber-300">
            {exp.concerns.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </Field>
      )}

      {exp.status === "buggy" && (
        <Field label="Failure">
          <span className="font-mono text-sm text-red-400">
            {exp.failureType}: {exp.failureMessage}
          </span>
        </Field>
      )}

      <Field label="Command">
        <code className="block break-all rounded bg-neutral-950 px-2 py-1 font-mono text-xs text-neutral-400">
          {exp.command ?? "—"}
        </code>
      </Field>
    </div>
  );
}
