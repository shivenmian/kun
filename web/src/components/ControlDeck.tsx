// "Mission Control" — the single cohesive live-steering surface for a Mode-A mission.
// It REGROUPS the previously-scattered steering pieces into one card (it does not
// rewrite their actions): Stop/Pause/Resume, the approval-gate arm/disarm toggle, the
// approval gate itself (when a proposal is pending), Fork, and Instruct. Only render
// this for a live Mode-A mission (App gates on isLiveModeA) — replay/observe stay
// steering-free. Controls disable by run_state (nothing to steer once stopped/finished).
import { Card, CardHeader, CardTitle, Button } from "./ui/primitives";
import { StopPauseControls } from "./StopPauseControls";
import { InstructBox } from "./InstructBox";
import { ApprovalGate } from "./ApprovalGate";
import { ApprovalToggle } from "./ApprovalToggle";
import { runStateColor, runStateLabel } from "../lib/status";
import type { MissionRuntimeState, PendingApproval } from "../lib/api";

export function ControlDeck({
  missionId,
  runtime,
  pendingApproval,
  selectedId,
  onChanged,
  onFork,
}: {
  missionId?: string;
  runtime: MissionRuntimeState | null;
  pendingApproval: PendingApproval | null;
  /** The node Fork would branch from (for the button label). */
  selectedId?: string;
  /** Bump the /state poll after any steering action. */
  onChanged: () => void;
  /** Open the existing ForkDialog (kept mounted in App). */
  onFork: () => void;
}) {
  const runState = runtime?.run_state;
  const isDone = runState === "stopped" || runState === "finished";
  const rsColor = runStateColor(runState);

  return (
    <Card className="flex flex-none flex-col">
      <CardHeader>
        <CardTitle>🛰 Mission Control</CardTitle>
        {runState && (
          <span className="text-[10px] font-semibold" style={{ color: rsColor }}>
            {runStateLabel(runState)}
          </span>
        )}
      </CardHeader>

      <div className="flex max-h-[58vh] flex-col gap-2.5 overflow-auto p-3">
        {/* run controls + arm/disarm */}
        <div className="flex flex-wrap items-center gap-2">
          <StopPauseControls
            missionId={missionId}
            runState={runState}
            onChanged={onChanged}
          />
          <Button
            size="sm"
            variant="outline"
            disabled={!missionId || isDone}
            onClick={onFork}
            title="Branch a new line of experiments from the selected node"
          >
            ⑂ Fork {selectedId ?? "node"}
          </Button>
        </div>

        <ApprovalToggle
          missionId={missionId}
          approvalRequired={runtime?.approval_required}
          disabled={isDone}
          onChanged={onChanged}
        />

        {/* the gate appears IN the deck when armed + a proposal is pending */}
        {pendingApproval && (
          <div className="-mx-3 border-y border-amber-700/40">
            <ApprovalGate missionId={missionId} pending={pendingApproval} onResolved={onChanged} />
          </div>
        )}

        {/* mid-run guidance (with the structured-bound builder it already ships) */}
        <div>
          <div className="mb-1 text-[10px] uppercase tracking-wide text-neutral-500">
            ✍ Instruct — mid-run guidance
          </div>
          <div className="rounded-md border border-neutral-800 bg-neutral-950/40">
            <InstructBox missionId={missionId} onSent={onChanged} disabled={isDone} />
          </div>
        </div>

        {isDone && (
          <div className="text-[10px] text-neutral-500">
            Loop {runStateLabel(runState)} — steering controls are disabled.
          </div>
        )}
      </div>
    </Card>
  );
}
