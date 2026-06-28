// CORE / HERO panel: mission-wide accumulated research memory — every constraint
// (human + learned), each showing text + structured bound + source + confidence +
// supporting experiments. A newly-learned constraint visibly lands here.
import type { Constraint } from "../types";

function BoundChip({ bound }: { bound?: Constraint["bound"] }) {
  if (!bound) return null;
  return (
    <span className="inline-flex items-center gap-1 rounded bg-neutral-950 px-1.5 py-0.5 font-mono text-[11px] text-rose-300 ring-1 ring-rose-500/30">
      reject&nbsp;<span className="text-neutral-400">{bound.param}</span>
      <span className="text-rose-400">{bound.op}</span>
      <span className="text-amber-300">{bound.value}</span>
    </span>
  );
}

export function ResearchMemoryPanel({
  constraints,
  highlightId,
  onSelectExperiment,
}: {
  constraints: Constraint[];
  highlightId?: string;
  onSelectExperiment?: (id: string) => void;
}) {
  if (constraints.length === 0) {
    return (
      <div className="p-4 text-sm text-neutral-500">
        No constraints learned yet. Failures and human forks accumulate research memory here.
      </div>
    );
  }
  return (
    <div className="space-y-2 p-2">
      {constraints.map((c) => {
        const learned = c.source === "learned";
        const accent = learned ? "#ef4444" : "#a855f7";
        const isNew = c.constraint_id === highlightId;
        return (
          <div
            key={c.constraint_id}
            className="rounded-md border bg-neutral-900/80 p-2.5 transition-shadow"
            style={{
              borderColor: `${accent}55`,
              boxShadow: isNew ? `0 0 0 2px ${accent}` : undefined,
            }}
          >
            <div className="mb-1 flex items-center gap-2">
              <span
                className="rounded px-1.5 py-0.5 text-[9px] font-bold uppercase"
                style={{ backgroundColor: `${accent}22`, color: accent }}
              >
                {learned ? "learned" : "human"}
              </span>
              <span className="font-mono text-[11px] text-neutral-400">{c.constraint_id}</span>
              {c.confidence && (
                <span className="ml-auto text-[10px] uppercase text-neutral-500">
                  conf: {c.confidence}
                </span>
              )}
            </div>
            <div className="mb-1.5 text-sm text-neutral-200">{c.text}</div>
            <div className="flex flex-wrap items-center gap-1.5">
              <BoundChip bound={c.bound} />
              {c.applies_to?.map((a) => (
                <span
                  key={a}
                  className="rounded bg-neutral-800 px-1.5 py-0.5 font-mono text-[10px] text-sky-300"
                >
                  {a}
                </span>
              ))}
            </div>
            {c.supporting_experiments && c.supporting_experiments.length > 0 && (
              <div className="mt-1.5 flex flex-wrap items-center gap-1 text-[11px] text-neutral-500">
                from:
                {c.supporting_experiments.map((e) => (
                  <button
                    key={e}
                    onClick={() => onSelectExperiment?.(e)}
                    className="font-mono text-neutral-400 underline-offset-2 hover:text-sky-300 hover:underline"
                  >
                    {e}
                  </button>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
