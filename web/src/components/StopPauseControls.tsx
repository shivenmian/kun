// Live human stop/pause/resume for a Mode-A mission (the carried-forward P0 control).
// Buttons POST /missions/{id}/stop {action} (CONTRACT §5.1 / §9.2 control.json); the
// current run_state comes from GET /state (CONTRACT §9.1) and gates the button states.
import { useState } from "react";
import { Button } from "./ui/primitives";
import { controlMission, type RunState } from "../lib/api";

export function StopPauseControls({
  missionId,
  runState,
  onChanged,
}: {
  missionId?: string;
  runState?: RunState;
  /** Bump the /state poll so the new run_state shows immediately. */
  onChanged?: () => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string>("");

  const send = async (action: "stop" | "pause" | "resume") => {
    if (!missionId) return;
    setBusy(action);
    setErr("");
    try {
      const r = await controlMission(missionId, action);
      if (!r.ok) setErr(`Error ${r.status}`);
      onChanged?.();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(null);
    }
  };

  const isPaused = runState === "paused";
  const isDone = runState === "stopped" || runState === "finished";

  return (
    <div className="flex items-center gap-1.5">
      {runState && (
        <span
          className={
            "rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide " +
            (isDone
              ? "bg-neutral-700/40 text-neutral-300"
              : isPaused
              ? "bg-amber-500/15 text-amber-300"
              : "bg-emerald-500/15 text-emerald-300")
          }
          title="Loop run_state (GET /state)"
        >
          {runState}
        </span>
      )}
      {isPaused ? (
        <Button
          size="sm"
          variant="outline"
          disabled={!missionId || isDone || busy != null}
          onClick={() => send("resume")}
        >
          ▶ Resume
        </Button>
      ) : (
        <Button
          size="sm"
          variant="outline"
          disabled={!missionId || isDone || busy != null}
          onClick={() => send("pause")}
        >
          ⏸ Pause
        </Button>
      )}
      <Button
        size="sm"
        variant="outline"
        className="border-red-700/60 text-red-300 hover:bg-red-900/30"
        disabled={!missionId || isDone || busy != null}
        onClick={() => send("stop")}
      >
        ⏹ Stop
      </Button>
      {err && <span className="text-[10px] text-red-400">{err}</span>}
    </div>
  );
}
