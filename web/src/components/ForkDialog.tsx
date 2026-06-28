// Visual fork affordance: pick a node, enter an instruction + optional constraint;
// on submit POST /missions/{id}/fork (record-only in P0). When the resulting
// fork_created/branch_created events arrive, the graph shows the new branch.
import { useState } from "react";
import { Button, Input, Textarea } from "./ui/primitives";
import { forkMission } from "../lib/api";
import type { Experiment } from "../types";

export function ForkDialog({
  missionId,
  parent,
  open,
  onClose,
  executes = false,
}: {
  missionId?: string;
  parent?: Experiment;
  open: boolean;
  onClose: () => void;
  /** Live Mode-A: the loop will EXECUTE the fork (CONTRACT §9.3), not just record it. */
  executes?: boolean;
}) {
  const [instruction, setInstruction] = useState("");
  const [param, setParam] = useState("");
  const [op, setOp] = useState(">");
  const [value, setValue] = useState("");
  const [status, setStatus] = useState<string>("");

  if (!open) return null;

  const submit = async () => {
    if (!missionId) {
      setStatus("No live mission — forks are recorded by the backend. Load a live mission first.");
      return;
    }
    const constraint =
      param && value
        ? {
            constraint_id: `human_${Date.now()}`,
            source: "human",
            text: `Ban ${param} ${op} ${value}.`,
            applies_to: [param],
            bound: { param, op, value: Number(value) },
          }
        : undefined;
    try {
      const r = await forkMission(missionId, {
        parent_experiment_id: parent?.id ?? "",
        instruction,
        constraint,
      });
      setStatus(
        r.ok
          ? executes
            ? "Fork queued — the loop will EXECUTE the next proposal on the new branch."
            : "Fork recorded — watch the graph for the new branch."
          : `Error ${r.status}`
      );
    } catch (e) {
      setStatus(`Request failed: ${String(e)}`);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-md rounded-lg border border-neutral-700 bg-neutral-900 p-4 shadow-xl">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-neutral-100">
            Fork from <span className="font-mono text-sky-300">{parent?.id ?? "(select a node)"}</span>
          </h3>
          <button onClick={onClose} className="text-neutral-500 hover:text-neutral-200">
            ✕
          </button>
        </div>

        {executes && (
          <div className="mb-3 rounded border border-emerald-700/50 bg-emerald-950/30 px-2 py-1.5 text-[11px] text-emerald-300">
            Live Mode-A: this fork will EXECUTE — the loop runs the next proposal on the new
            branch (not record-only).
          </div>
        )}

        <label className="mb-1 block text-[10px] uppercase tracking-wide text-neutral-500">
          Instruction
        </label>
        <Textarea
          rows={3}
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          placeholder="e.g. Keep augmentation, ban dropout > 0.4, try weight decay."
          className="mb-3"
        />

        <label className="mb-1 block text-[10px] uppercase tracking-wide text-neutral-500">
          Optional constraint (structured bound)
        </label>
        <div className="mb-3 flex gap-2">
          <Input
            placeholder="param (e.g. dropout)"
            value={param}
            onChange={(e) => setParam(e.target.value)}
          />
          <select
            value={op}
            onChange={(e) => setOp(e.target.value)}
            className="h-9 rounded-md border border-neutral-700 bg-neutral-950 px-2 text-sm text-neutral-100"
          >
            <option value=">">&gt;</option>
            <option value=">=">&ge;</option>
            <option value="<">&lt;</option>
            <option value="<=">&le;</option>
            <option value="==">=</option>
          </select>
          <Input
            placeholder="value"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            className="w-24"
          />
        </div>

        {status && <div className="mb-2 text-xs text-amber-300">{status}</div>}

        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!instruction}>
            {executes ? "Fork & run" : "Fork"}
          </Button>
        </div>
      </div>
    </div>
  );
}
