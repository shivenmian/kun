// Mission History — a mission-control panel listing every executed mission as
// clickable summary rows (CONTRACT §5.2 enriched GET /missions). A click routes
// into the SAME launch flow MissionLauncher uses (onLaunch):
//   - active live mission  → { kind:"live",    missionId }  (hydrate + SSE)
//   - finished / external  → { kind:"observe", missionId }  (register then SSE; works
//                                                             for any mission with a log)
// Codes defensively against a partial backend shape: getMissions() never throws and
// returns [] on error, so this renders a clean empty-state with no backend.
import { useCallback, useEffect, useState } from "react";
import { getMissions, registerMission, type MissionSummary } from "../lib/api";
import type { LaunchChoice } from "./MissionLauncher";
import { Badge, Button, Card, CardBody } from "./ui/primitives";
import { runStateColor, runStateLabel } from "../lib/status";
import { fmtMetric, relativeTime } from "../lib/utils";

/** Decide how a row routes into the launch flow (mirrors MissionLauncher). */
function routeFor(m: MissionSummary): LaunchChoice {
  const rs = m.run_state ?? "";
  const active = rs === "run" || rs === "running" || rs === "paused" || rs === "pause";
  if (m.mode === "live" && active) return { kind: "live", missionId: m.mission_id };
  // finished / stopped / external / unknown → observe (hydrate via /events + tail /stream)
  return { kind: "observe", missionId: m.mission_id };
}

export function MissionHistory({
  onLaunch,
  model,
}: {
  onLaunch: (c: LaunchChoice, model: string) => void;
  model: string;
}) {
  const [missions, setMissions] = useState<MissionSummary[] | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const rows = await getMissions(); // never throws; [] on error
    setMissions(rows);
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const open = async (m: MissionSummary) => {
    const choice = routeFor(m);
    if (choice.kind === "observe") {
      // Best-effort register so the backend tails the log (harmless if already known).
      try {
        await registerMission(m.mission_id);
      } catch {
        /* ignore — open the stream anyway */
      }
    }
    onLaunch(choice, model);
  };

  return (
    <Card>
      <CardBody>
        <div className="mb-2 flex items-center justify-between">
          <div>
            <div className="text-sm font-semibold text-neutral-100">Mission history</div>
            <div className="text-xs text-neutral-500">
              Every executed mission — click a row to open it.
            </div>
          </div>
          <Button size="sm" variant="ghost" onClick={() => void load()} disabled={loading}>
            {loading ? "Refreshing…" : "↻ Refresh"}
          </Button>
        </div>

        {missions == null ? (
          <div className="py-6 text-center text-xs text-neutral-500">Loading missions…</div>
        ) : missions.length === 0 ? (
          <div className="py-6 text-center text-xs text-neutral-500">
            No missions yet. Create or observe one to get started.
          </div>
        ) : (
          <div className="overflow-auto rounded-md border border-neutral-800">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-neutral-800 text-left text-[10px] uppercase tracking-wide text-neutral-500">
                  <th className="px-3 py-2">Mission</th>
                  <th className="px-3 py-2">State</th>
                  <th className="px-3 py-2">Mode</th>
                  <th className="px-3 py-2 text-right">Exps</th>
                  <th className="px-3 py-2">Best</th>
                  <th className="px-3 py-2 text-right">Updated</th>
                </tr>
              </thead>
              <tbody>
                {missions.map((m) => {
                  const best = m.best?.metric;
                  const bestVal = typeof best?.value === "number" ? best.value : undefined;
                  return (
                    <tr
                      key={m.mission_id}
                      onClick={() => void open(m)}
                      title={`Open ${m.mission_id}`}
                      className="cursor-pointer border-b border-neutral-900 last:border-0 hover:bg-neutral-800/60"
                    >
                      <td className="max-w-[16rem] px-3 py-1.5">
                        <div className="truncate text-neutral-100">
                          {m.name || m.mission_id}
                        </div>
                        {m.name && (
                          <div className="truncate font-mono text-[10px] text-neutral-600">
                            {m.mission_id}
                          </div>
                        )}
                      </td>
                      <td className="px-3 py-1.5">
                        {m.run_state ? (
                          <Badge color={runStateColor(m.run_state)}>
                            {runStateLabel(m.run_state)}
                          </Badge>
                        ) : (
                          <span className="text-neutral-600">—</span>
                        )}
                      </td>
                      <td className="px-3 py-1.5 text-xs text-neutral-400">{m.mode ?? "—"}</td>
                      <td className="px-3 py-1.5 text-right font-mono text-neutral-300">
                        {typeof m.experiments_count === "number" ? m.experiments_count : "—"}
                      </td>
                      <td className="px-3 py-1.5 text-xs">
                        {bestVal != null ? (
                          <span className="font-mono text-amber-400">
                            {fmtMetric(bestVal)}
                            {best?.name && (
                              <span className="ml-1 text-[10px] text-neutral-500">{best.name}</span>
                            )}
                          </span>
                        ) : (
                          <span className="text-neutral-600">—</span>
                        )}
                      </td>
                      <td className="px-3 py-1.5 text-right text-[11px] text-neutral-500">
                        {relativeTime(m.updated_at ?? undefined)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </CardBody>
    </Card>
  );
}
