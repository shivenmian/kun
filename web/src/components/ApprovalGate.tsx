// Human approval gate for a live Mode-A mission. Shown when GET /state reports a
// pending_approval (or the event stream has an unresolved experiment_proposed while the
// approval gate is on — CONTRACT §9.1). Presents the proposed experiment and offers:
//   Approve         → POST .../approve {edited:false}
//   Edit & Approve  → tweak `changes` → POST .../approve {edited:true, changes}
//   Reject          → POST .../reject {reason, replacement_changes?}
// (CONTRACT §5.1 / §9.3.) The loop holds the node until one of these resolves it.
import { useState } from "react";
import { Button, Textarea } from "./ui/primitives";
import { approveExperiment, rejectExperiment, type PendingApproval } from "../lib/api";

type Mode = "idle" | "edit" | "reject";

export function ApprovalGate({
  missionId,
  pending,
  onResolved,
}: {
  missionId?: string;
  pending: PendingApproval;
  /** Bump the /state poll so the gate clears once the backend records the decision. */
  onResolved?: () => void;
}) {
  const [mode, setMode] = useState<Mode>("idle");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [changesText, setChangesText] = useState(() =>
    JSON.stringify(pending.changes ?? {}, null, 2)
  );
  const [reason, setReason] = useState("");
  const [replacementText, setReplacementText] = useState("");

  const expId = pending.experiment_id;

  const guard = (): boolean => {
    if (!missionId) {
      setStatus("No live mission.");
      return false;
    }
    return true;
  };

  const approve = async (edited: boolean) => {
    if (!guard()) return;
    let changes: Record<string, unknown> | undefined;
    if (edited) {
      try {
        changes = JSON.parse(changesText) as Record<string, unknown>;
      } catch {
        setStatus("Edited changes must be valid JSON.");
        return;
      }
    }
    setBusy(true);
    setStatus("");
    try {
      const r = await approveExperiment(missionId!, expId, edited ? { edited, changes } : { edited });
      setStatus(r.ok ? "Approved — the loop will run it." : `Error ${r.status}`);
      onResolved?.();
    } catch (e) {
      setStatus(`Request failed: ${String(e)}`);
    } finally {
      setBusy(false);
    }
  };

  const reject = async () => {
    if (!guard()) return;
    if (!reason.trim()) {
      setStatus("A reject reason is required.");
      return;
    }
    let replacement_changes: Record<string, unknown> | undefined;
    if (replacementText.trim()) {
      try {
        replacement_changes = JSON.parse(replacementText) as Record<string, unknown>;
      } catch {
        setStatus("Replacement changes must be valid JSON.");
        return;
      }
    }
    setBusy(true);
    setStatus("");
    try {
      const r = await rejectExperiment(missionId!, expId, {
        reason: reason.trim(),
        replacement_changes,
      });
      setStatus(r.ok ? "Rejected." : `Error ${r.status}`);
      onResolved?.();
    } catch (e) {
      setStatus(`Request failed: ${String(e)}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="border-b border-amber-700/50 bg-amber-950/30 px-4 py-3">
      <div className="mb-2 flex items-center gap-2">
        <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-amber-300">
          Approval required
        </span>
        <span className="font-mono text-sm font-semibold text-neutral-100">{expId}</span>
        {pending.operator && (
          <span className="rounded bg-neutral-800 px-1.5 py-0.5 text-[10px] font-bold uppercase text-sky-300">
            {pending.operator}
          </span>
        )}
      </div>

      {pending.hypothesis && (
        <div className="mb-2 text-xs text-neutral-300">{pending.hypothesis}</div>
      )}

      {mode === "idle" && (
        <div className="mb-2 flex flex-wrap gap-1.5">
          {Object.entries(pending.changes ?? {}).map(([k, v]) => (
            <span
              key={k}
              className="rounded bg-neutral-800 px-1.5 py-0.5 font-mono text-xs text-sky-300"
            >
              {k} = {JSON.stringify(v)}
            </span>
          ))}
          {Object.keys(pending.changes ?? {}).length === 0 && (
            <span className="text-xs text-neutral-500">(no changes payload)</span>
          )}
        </div>
      )}

      {mode === "edit" && (
        <div className="mb-2">
          <label className="mb-1 block text-[10px] uppercase tracking-wide text-neutral-500">
            Edit changes (JSON)
          </label>
          <Textarea
            rows={5}
            value={changesText}
            onChange={(e) => setChangesText(e.target.value)}
            className="font-mono text-xs"
          />
        </div>
      )}

      {mode === "reject" && (
        <div className="mb-2 space-y-2">
          <div>
            <label className="mb-1 block text-[10px] uppercase tracking-wide text-neutral-500">
              Reason (required)
            </label>
            <Textarea
              rows={2}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Why reject this proposal?"
            />
          </div>
          <div>
            <label className="mb-1 block text-[10px] uppercase tracking-wide text-neutral-500">
              Replacement changes (optional JSON — runs a human 'improve')
            </label>
            <Textarea
              rows={3}
              value={replacementText}
              onChange={(e) => setReplacementText(e.target.value)}
              placeholder='e.g. {"learning_rate": 0.002}'
              className="font-mono text-xs"
            />
          </div>
        </div>
      )}

      {status && <div className="mb-2 text-[11px] text-amber-200">{status}</div>}

      <div className="flex flex-wrap gap-2">
        {mode === "idle" && (
          <>
            <Button size="sm" disabled={!missionId || busy} onClick={() => approve(false)}>
              Approve
            </Button>
            <Button size="sm" variant="outline" disabled={busy} onClick={() => setMode("edit")}>
              Edit & Approve
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="border-red-700/60 text-red-300 hover:bg-red-900/30"
              disabled={busy}
              onClick={() => setMode("reject")}
            >
              Reject
            </Button>
          </>
        )}
        {mode === "edit" && (
          <>
            <Button size="sm" disabled={!missionId || busy} onClick={() => approve(true)}>
              Approve edited
            </Button>
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => setMode("idle")}>
              Cancel
            </Button>
          </>
        )}
        {mode === "reject" && (
          <>
            <Button
              size="sm"
              className="bg-red-600 hover:bg-red-500"
              disabled={!missionId || busy}
              onClick={reject}
            >
              Confirm reject
            </Button>
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => setMode("idle")}>
              Cancel
            </Button>
          </>
        )}
      </div>
    </div>
  );
}
