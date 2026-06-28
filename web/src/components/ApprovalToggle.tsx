// Arm / disarm the human approval gate from the cockpit (previously only settable via
// curl). Bound to runtime.approval_required (GET /state, CONTRACT §9.1). Toggling POSTs
// the control endpoint with {action:"resume", approval_required:<bool>} (reusing the
// controlMission/stop wrapper, CONTRACT §5.1 / §9.2) and refreshes the runtime poll so
// the new flag — and any resulting pending_approval — shows immediately.
import { useState } from "react";
import { controlMission } from "../lib/api";

export function ApprovalToggle({
  missionId,
  approvalRequired,
  disabled,
  onChanged,
  compact = false,
}: {
  missionId?: string;
  approvalRequired?: boolean;
  /** Disabled once the loop is stopped/finished (nothing left to gate). */
  disabled?: boolean;
  /** Bump the /state poll so the armed/disarmed flag shows immediately. */
  onChanged?: () => void;
  /** Slim inline variant for the topbar instrument strip (vs the deck card). */
  compact?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const on = !!approvalRequired;

  const toggle = async () => {
    if (!missionId || busy) return;
    const next = !on;
    setBusy(true);
    setErr("");
    try {
      // No action: set the approval flag WITHOUT changing run_state, so arming the
      // gate never un-pauses a paused mission (CONTRACT §5.1 / §9.2).
      const r = await controlMission(missionId, null, { approval_required: next });
      if (!r.ok) setErr(`Error ${r.status}`);
      onChanged?.();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  const Switch = (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      disabled={!missionId || disabled || busy}
      onClick={toggle}
      title={on ? "Disarm approval gate" : "Arm approval gate"}
      className={
        "relative h-5 w-9 flex-none rounded-full transition-colors disabled:opacity-40 " +
        (on ? "bg-amber-500" : "bg-neutral-700")
      }
    >
      <span
        className={
          "absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all " +
          (on ? "left-[1.125rem]" : "left-0.5")
        }
      />
    </button>
  );

  if (compact) {
    // Topbar instrument: tiny label + switch, matching the Stat strip.
    return (
      <div className="flex flex-col" title={on ? "Proposals wait for you" : "Loop runs autonomously"}>
        <span className="text-[9px] uppercase tracking-wide text-neutral-500">Approval gate</span>
        <div className="flex items-center gap-1.5">
          {Switch}
          <span className={"text-xs font-semibold " + (on ? "text-amber-400" : "text-neutral-500")}>
            {on ? "armed" : "off"}
          </span>
          {err && <span className="text-[10px] text-red-400">{err}</span>}
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-between gap-2 rounded-md border border-neutral-800 bg-neutral-950/60 px-2.5 py-2">
      <div className="min-w-0">
        <div className="text-xs font-medium text-neutral-200">Approval gate</div>
        <div className="text-[10px] text-neutral-500">
          {on ? "Proposals wait for you" : "Loop runs autonomously"}
        </div>
      </div>
      <div className="flex items-center gap-1.5">
        {err && <span className="text-[10px] text-red-400">{err}</span>}
        <button
          type="button"
          role="switch"
          aria-checked={on}
          disabled={!missionId || disabled || busy}
          onClick={toggle}
          title={on ? "Disarm approval gate" : "Arm approval gate"}
          className={
            "relative h-5 w-9 flex-none rounded-full transition-colors disabled:opacity-40 " +
            (on ? "bg-amber-500" : "bg-neutral-700")
          }
        >
          <span
            className={
              "absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all " +
              (on ? "left-[1.125rem]" : "left-0.5")
            }
          />
        </button>
      </div>
    </div>
  );
}
