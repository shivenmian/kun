// CORE / HERO panel: mission-wide accumulated research memory, rendered as TWO TIERS
// (CONTRACT §3 / §9.1):
//   - HARD constraints  — constraint object WITH a `bound` → planner hard-rejects.
//   - SOFT lessons      — constraint object with NO `bound` → bias-only positive findings
//                         (e.g. "cosine: +0.012"). Never hard-reject.
// Each row shows text + structured bound (hard only) + source + confidence (with a visible
// medium→high sharpening when it rises) + supporting experiments. A newly-landed or
// freshly-sharpened constraint highlights.
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

const CONF_COLOR: Record<string, string> = {
  low: "#71717a",
  medium: "#eab308",
  high: "#22c55e",
};

function ConfidenceChip({ c }: { c: Constraint }) {
  if (!c.confidence) return null;
  const color = CONF_COLOR[c.confidence] ?? "#71717a";
  return (
    <span className="ml-auto flex items-center gap-1 text-[10px] uppercase">
      {c.priorConfidence && (
        <>
          <span className="text-neutral-600 line-through">{c.priorConfidence}</span>
          <span className="text-neutral-500">→</span>
        </>
      )}
      <span style={{ color }} className={c.priorConfidence ? "font-bold" : ""}>
        {c.confidence}
        {c.priorConfidence ? " ↑" : ""}
      </span>
    </span>
  );
}

function ConstraintCard({
  c,
  tier,
  highlightId,
  onSelectExperiment,
}: {
  c: Constraint;
  tier: "hard" | "soft";
  highlightId?: string;
  onSelectExperiment?: (id: string) => void;
}) {
  const learned = c.source === "learned";
  // Hard tier = rose/red (it rejects); soft tier = emerald (a positive bias).
  const accent = tier === "hard" ? (learned ? "#ef4444" : "#f97316") : "#10b981";
  const isNew = c.constraint_id === highlightId;
  return (
    <div
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
        <ConfidenceChip c={c} />
      </div>
      <div className="mb-1.5 text-sm text-neutral-200">{c.text}</div>
      <div className="flex flex-wrap items-center gap-1.5">
        <BoundChip bound={c.bound} />
        {tier === "soft" && (
          <span className="rounded bg-emerald-950 px-1.5 py-0.5 text-[10px] font-medium text-emerald-300 ring-1 ring-emerald-500/30">
            bias only
          </span>
        )}
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
}

function TierHeader({ label, count, hint }: { label: string; count: number; hint: string }) {
  return (
    <div className="flex items-baseline gap-2 px-1 pt-1">
      <span className="text-[10px] font-bold uppercase tracking-wide text-neutral-400">
        {label}
      </span>
      <span className="text-[10px] text-neutral-600">{count}</span>
      <span className="ml-auto text-[10px] text-neutral-600">{hint}</span>
    </div>
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
  // Two tiers, split purely on the presence of a structured `bound` (CONTRACT §3).
  const hard = constraints.filter((c) => c.bound);
  const soft = constraints.filter((c) => !c.bound);

  if (constraints.length === 0) {
    return (
      <div className="p-4 text-sm text-neutral-500">
        No research memory yet. Failures and human forks accumulate hard constraints; positive
        findings accumulate soft lessons here.
      </div>
    );
  }

  return (
    <div className="space-y-3 p-2">
      <div className="space-y-2">
        <TierHeader label="Hard constraints" count={hard.length} hint="hard-reject" />
        {hard.length === 0 ? (
          <div className="px-1 text-[11px] text-neutral-600">None yet.</div>
        ) : (
          hard.map((c) => (
            <ConstraintCard
              key={c.constraint_id}
              c={c}
              tier="hard"
              highlightId={highlightId}
              onSelectExperiment={onSelectExperiment}
            />
          ))
        )}
      </div>

      <div className="space-y-2">
        <TierHeader label="Soft lessons" count={soft.length} hint="bias only" />
        {soft.length === 0 ? (
          <div className="px-1 text-[11px] text-neutral-600">
            None yet — positive findings (e.g. "cosine: +0.012") will land here.
          </div>
        ) : (
          soft.map((c) => (
            <ConstraintCard
              key={c.constraint_id}
              c={c}
              tier="soft"
              highlightId={highlightId}
              onSelectExperiment={onSelectExperiment}
            />
          ))
        )}
      </div>
    </div>
  );
}
