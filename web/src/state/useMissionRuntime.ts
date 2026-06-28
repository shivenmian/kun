// Poll GET /missions/{id}/state (~1s) to drive the live-steering surfaces:
// the approval gate (pending_approval) and the run-state of the Stop/Pause controls.
// (CONTRACT §9.1.) Only enable for a LIVE Mode-A mission; returns null otherwise so
// replay/observe views never poll. Tolerant of a missing/partial endpoint — getMissionState
// already swallows errors and returns null, so we simply keep the last good snapshot.
import { useCallback, useEffect, useRef, useState } from "react";
import { getMissionState, type MissionRuntimeState } from "../lib/api";

export function useMissionRuntime(
  missionId: string | undefined,
  enabled: boolean,
  intervalMs = 1000
): { runtime: MissionRuntimeState | null; refresh: () => void } {
  const [runtime, setRuntime] = useState<MissionRuntimeState | null>(null);
  const [nonce, setNonce] = useState(0);
  const refresh = useCallback(() => setNonce((n) => n + 1), []);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    if (!enabled || !missionId) {
      setRuntime(null);
      return;
    }
    let cancelled = false;
    const poll = async () => {
      const s = await getMissionState(missionId);
      if (cancelled) return;
      if (s) setRuntime(s); // keep last snapshot if the endpoint is briefly unavailable
      timer.current = window.setTimeout(poll, intervalMs);
    };
    poll();
    return () => {
      cancelled = true;
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [missionId, enabled, intervalMs, nonce]);

  return { runtime, refresh };
}
