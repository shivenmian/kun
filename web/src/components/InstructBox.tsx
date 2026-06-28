// Inject mid-run guidance into a live Mode-A mission. Text is the primary path →
// POST /missions/{id}/instruct {text, applies_from?, bound?} (CONTRACT §5.1 / §9.3).
// A structured `bound` is optional (e.g. "ban dropout > 0.4"); when present the loop can
// hard-reject against it like a constraint, otherwise the text is a soft bias.
import { useState } from "react";
import { Button, Input, Textarea } from "./ui/primitives";
import { instructMission } from "../lib/api";

export function InstructBox({
  missionId,
  onSent,
  disabled,
}: {
  missionId?: string;
  onSent?: () => void;
  /** Disabled once the loop is stopped/finished (no upcoming proposals to bias). */
  disabled?: boolean;
}) {
  const [text, setText] = useState("");
  const [showBound, setShowBound] = useState(false);
  const [param, setParam] = useState("");
  const [op, setOp] = useState(">");
  const [value, setValue] = useState("");
  const [appliesFrom, setAppliesFrom] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!missionId || !text.trim() || disabled) return;
    const bound =
      showBound && param && value
        ? { param, op, value: Number(value) }
        : undefined;
    setBusy(true);
    setStatus("");
    try {
      const r = await instructMission(missionId, {
        text: text.trim(),
        applies_from: appliesFrom.trim() || undefined,
        bound,
      });
      if (r.ok) {
        setStatus("Instruction sent — the planner will apply it on upcoming proposals.");
        setText("");
        setParam("");
        setValue("");
      } else {
        setStatus(`Error ${r.status}`);
      }
      onSent?.();
    } catch (e) {
      setStatus(`Request failed: ${String(e)}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="p-3">
      <Textarea
        rows={2}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Inject guidance, e.g. 'Prefer SGD over Adam from here; keep augmentation on.'"
        className="mb-2"
      />

      <button
        type="button"
        onClick={() => setShowBound((v) => !v)}
        className="mb-2 text-[10px] uppercase tracking-wide text-neutral-500 hover:text-neutral-300"
      >
        {showBound ? "▾" : "▸"} Optional structured bound (hard-reject)
      </button>

      {showBound && (
        <div className="mb-2 flex gap-2">
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
      )}

      <div className="mb-2 flex items-center gap-2">
        <span className="text-[10px] uppercase tracking-wide text-neutral-500">applies from</span>
        <Input
          placeholder="exp_id (optional)"
          value={appliesFrom}
          onChange={(e) => setAppliesFrom(e.target.value)}
          className="h-7 w-40 text-xs"
        />
      </div>

      {status && <div className="mb-2 text-[11px] text-amber-300">{status}</div>}

      <div className="flex justify-end">
        <Button size="sm" onClick={submit} disabled={!missionId || !text.trim() || busy || disabled}>
          Send instruction
        </Button>
      </div>
    </div>
  );
}
