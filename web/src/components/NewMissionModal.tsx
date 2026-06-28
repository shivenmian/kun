// New Mission modal — the first real create form (today missions are only
// creatable via curl). Builds the mission_created payload (CONTRACT §2) and POSTs
// it to createMission. On "create & start" it optionally flips the approval gate
// ON (controlMission resume + approval_required) BEFORE startMission, then selects
// the new mission as a live Mode-A run so the cockpit streams it in place.
import { useState } from "react";
import {
  createMission,
  startMission,
  controlMission,
  type LaunchChoice,
} from "../lib/api";
import { Button, Input, Label, Modal, Select, Textarea } from "./ui/primitives";
import { cn } from "../lib/utils";

const ALLOWED_CHANGES = [
  "learning_rate",
  "optimizer",
  "dropout",
  "batch_size",
  "conv_channels",
  "weight_decay",
  "augmentation",
  "scheduler",
] as const;

const OPS = [">", ">=", "<", "<=", "=="];

interface ConstraintRow {
  param: string;
  op: string;
  value: string;
}

export function NewMissionModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  /** Called once the mission exists (and was started, if chosen) — App selects it. */
  onCreated: (c: LaunchChoice) => void;
}) {
  const [name, setName] = useState("");
  const [goal, setGoal] = useState("");
  const [metric, setMetric] = useState("val_accuracy");
  const [direction, setDirection] = useState<"maximize" | "minimize">("maximize");
  const [target, setTarget] = useState("");
  const [maxExperiments, setMaxExperiments] = useState("10");
  const [maxRuntime, setMaxRuntime] = useState("120");
  const [adapter, setAdapter] = useState("tiny_cnn");
  const [allowed, setAllowed] = useState<string[]>([
    "learning_rate",
    "optimizer",
    "dropout",
  ]);
  const [patcher, setPatcher] = useState<"config-patch" | "agent-edit">("config-patch");
  const [plannerModel, setPlannerModel] = useState("claude-opus-4-8");
  const [editorModel, setEditorModel] = useState("claude-opus-4-8");
  const [approvalOn, setApprovalOn] = useState(false);
  const [constraints, setConstraints] = useState<ConstraintRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");

  const toggleAllowed = (c: string) =>
    setAllowed((prev) => (prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]));

  const addConstraint = () =>
    setConstraints((prev) => [...prev, { param: "", op: ">", value: "" }]);
  const updateConstraint = (i: number, patch: Partial<ConstraintRow>) =>
    setConstraints((prev) => prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  const removeConstraint = (i: number) =>
    setConstraints((prev) => prev.filter((_, idx) => idx !== i));

  const buildPayload = (): Record<string, unknown> => {
    const objective: Record<string, unknown> = { metric, direction };
    if (target.trim() && !Number.isNaN(Number(target))) objective.target = Number(target);

    const builtConstraints = constraints
      .filter((r) => r.param.trim() && r.value.trim() && !Number.isNaN(Number(r.value)))
      .map((r) => ({
        constraint_id: `human_${Date.now()}_${r.param}`,
        source: "human",
        text: `Ban ${r.param} ${r.op} ${r.value}.`,
        applies_to: [r.param],
        bound: { param: r.param, op: r.op, value: Number(r.value) },
      }));

    const payload: Record<string, unknown> = {
      name: name.trim() || "Untitled mission",
      goal: goal.trim() || undefined,
      objective,
      budget: {
        max_experiments: Number(maxExperiments) || undefined,
        max_runtime_per_experiment_sec: Number(maxRuntime) || undefined,
      },
      adapter,
      allowed_changes: allowed,
      patcher,
      planner_model: plannerModel.trim() || undefined,
      editor_model: editorModel.trim() || undefined,
      model: plannerModel.trim() || undefined, // surfaced as the driver model in the topbar
    };
    if (builtConstraints.length) payload.constraints = builtConstraints;
    return payload;
  };

  const submit = async (start: boolean) => {
    setBusy(true);
    setStatus("Creating mission…");
    try {
      const res = await createMission(buildPayload());
      if (!res.ok) {
        setStatus(`Create failed (${res.status})`);
        setBusy(false);
        return;
      }
      const { mission_id } = (await res.json()) as { mission_id: string };

      if (start) {
        if (approvalOn) {
          // Flip the approval gate ON before the loop starts (CONTRACT §9.2).
          setStatus("Enabling approval gate…");
          try {
            await controlMission(mission_id, "resume", { approval_required: true });
          } catch {
            /* best-effort — start anyway */
          }
        }
        setStatus("Starting loop…");
        await startMission(mission_id);
        onCreated({ kind: "live", missionId: mission_id });
      } else {
        // Created but not started — open it (observe view) so it appears in place.
        onCreated({ kind: "observe", missionId: mission_id });
      }
      reset();
    } catch (e) {
      setStatus(`Request failed: ${String(e)}`);
    } finally {
      setBusy(false);
    }
  };

  const reset = () => {
    setStatus("");
    onClose();
  };

  return (
    <Modal
      open={open}
      onClose={busy ? () => {} : reset}
      size="lg"
      title="New mission"
      subtitle="Define the objective, budget and search space, then create or launch the loop."
      footer={
        <>
          {status && <span className="mr-auto self-center text-xs text-amber-300">{status}</span>}
          <Button variant="outline" onClick={reset} disabled={busy}>
            Cancel
          </Button>
          <Button variant="outline" onClick={() => void submit(false)} disabled={busy}>
            Create only
          </Button>
          <Button onClick={() => void submit(true)} disabled={busy}>
            Create &amp; start
          </Button>
        </>
      }
    >
      <div className="grid grid-cols-2 gap-3">
        <div className="col-span-2">
          <Label>Name</Label>
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Fashion-MNIST CNN Accuracy Sprint" />
        </div>
        <div className="col-span-2">
          <Label>Goal</Label>
          <Textarea
            rows={2}
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            placeholder="Maximize validation accuracy on Fashion-MNIST within budget."
          />
        </div>

        <div>
          <Label>Objective metric</Label>
          <Input value={metric} onChange={(e) => setMetric(e.target.value)} placeholder="val_accuracy" />
        </div>
        <div className="flex gap-2">
          <div className="flex-1">
            <Label>Direction</Label>
            <Select
              value={direction}
              onChange={(e) => setDirection(e.target.value as "maximize" | "minimize")}
              className="w-full"
            >
              <option value="maximize">maximize</option>
              <option value="minimize">minimize</option>
            </Select>
          </div>
          <div className="w-24">
            <Label>Target</Label>
            <Input value={target} onChange={(e) => setTarget(e.target.value)} placeholder="0.92" />
          </div>
        </div>

        <div>
          <Label>Max experiments</Label>
          <Input value={maxExperiments} onChange={(e) => setMaxExperiments(e.target.value)} />
        </div>
        <div>
          <Label>Max runtime / exp (sec)</Label>
          <Input value={maxRuntime} onChange={(e) => setMaxRuntime(e.target.value)} />
        </div>

        <div>
          <Label>Adapter</Label>
          <Input value={adapter} onChange={(e) => setAdapter(e.target.value)} />
        </div>
        <div>
          <Label>Patcher</Label>
          <Select
            value={patcher}
            onChange={(e) => setPatcher(e.target.value as "config-patch" | "agent-edit")}
            className="w-full"
          >
            <option value="config-patch">config-patch</option>
            <option value="agent-edit">agent-edit</option>
          </Select>
        </div>

        <div>
          <Label>Planner model</Label>
          <Input value={plannerModel} onChange={(e) => setPlannerModel(e.target.value)} />
        </div>
        <div>
          <Label>Editor model</Label>
          <Input value={editorModel} onChange={(e) => setEditorModel(e.target.value)} />
        </div>

        <div className="col-span-2">
          <Label>Allowed changes</Label>
          <div className="flex flex-wrap gap-1.5">
            {ALLOWED_CHANGES.map((c) => {
              const on = allowed.includes(c);
              return (
                <button
                  key={c}
                  type="button"
                  onClick={() => toggleAllowed(c)}
                  className={cn(
                    "rounded-full border px-2.5 py-1 text-[11px] transition-colors",
                    on
                      ? "border-sky-600 bg-sky-600/20 text-sky-200"
                      : "border-neutral-700 text-neutral-400 hover:bg-neutral-800"
                  )}
                >
                  {c}
                </button>
              );
            })}
          </div>
        </div>

        <div className="col-span-2">
          <div className="mb-1 flex items-center justify-between">
            <Label className="mb-0">Initial constraints (optional)</Label>
            <button
              type="button"
              onClick={addConstraint}
              className="text-[11px] text-sky-400 hover:text-sky-300"
            >
              + add
            </button>
          </div>
          {constraints.length === 0 && (
            <div className="text-[11px] text-neutral-600">No constraints — the loop searches freely.</div>
          )}
          <div className="flex flex-col gap-1.5">
            {constraints.map((r, i) => (
              <div key={i} className="flex gap-1.5">
                <Input
                  placeholder="param (e.g. dropout)"
                  value={r.param}
                  onChange={(e) => updateConstraint(i, { param: e.target.value })}
                />
                <Select value={r.op} onChange={(e) => updateConstraint(i, { op: e.target.value })}>
                  {OPS.map((o) => (
                    <option key={o} value={o}>
                      {o}
                    </option>
                  ))}
                </Select>
                <Input
                  className="w-24"
                  placeholder="value"
                  value={r.value}
                  onChange={(e) => updateConstraint(i, { value: e.target.value })}
                />
                <button
                  type="button"
                  onClick={() => removeConstraint(i)}
                  className="flex-none px-1 text-neutral-500 hover:text-red-400"
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        </div>

        <label className="col-span-2 flex cursor-pointer items-center gap-2 rounded-md border border-neutral-800 bg-neutral-950/60 px-3 py-2 text-xs text-neutral-300">
          <input
            type="checkbox"
            checked={approvalOn}
            onChange={(e) => setApprovalOn(e.target.checked)}
            className="h-3.5 w-3.5 accent-sky-500"
          />
          Start with the approval gate ON — every proposed experiment waits for a human OK.
        </label>
      </div>
    </Modal>
  );
}
