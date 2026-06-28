// Left rail of the cockpit shell: the persistent mission navigator. Wraps
// MissionHistory (the grouped list) with the rail chrome — entry-point buttons
// (+ New / Observe / Replay), a search/filter box, a refresh, and a collapse
// toggle. Owns the GET /missions poll and the click→open routing (registering
// external missions before observing). Selecting a row loads it IN PLACE via
// onSelect — App's data-source effect re-subscribes; the shell never unmounts.
import { useCallback, useEffect, useImperativeHandle, useMemo, useState, forwardRef } from "react";
import { getMissions, registerMission, type MissionSummary, type LaunchChoice } from "../lib/api";
import { Button, Input } from "./ui/primitives";
import { MissionHistory, routeFor } from "./MissionHistory";
import { cn } from "../lib/utils";

export interface MissionNavigatorHandle {
  refresh: () => void;
}

export const MissionNavigator = forwardRef<
  MissionNavigatorHandle,
  {
    activeMissionId?: string;
    collapsed: boolean;
    onToggleCollapse: () => void;
    onSelect: (c: LaunchChoice) => void;
    onNew: () => void;
    onObserve: () => void;
    onReplay: () => void;
  }
>(function MissionNavigator(
  { activeMissionId, collapsed, onToggleCollapse, onSelect, onNew, onObserve, onReplay },
  ref
) {
  const [missions, setMissions] = useState<MissionSummary[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    const rows = await getMissions(); // never throws; [] on error
    setMissions(rows);
    setLoading(false);
  }, []);

  useImperativeHandle(ref, () => ({ refresh: () => void load() }), [load]);

  // Initial load + light polling so running missions stay fresh (pulse, badges).
  useEffect(() => {
    void load();
    const t = window.setInterval(() => void load(), 5000);
    return () => window.clearInterval(t);
  }, [load]);

  // Cross-mission attention: how many missions currently need a human (armed gate with
  // a pending proposal — GET /missions §5.2 pending_approval).
  const needsHuman = useMemo(
    () => (missions ?? []).filter((m) => m.pending_approval).length,
    [missions]
  );

  const filtered = useMemo(() => {
    const rows = missions ?? [];
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(
      (m) =>
        m.mission_id.toLowerCase().includes(q) ||
        (m.name ?? "").toLowerCase().includes(q)
    );
  }, [missions, query]);

  const open = useCallback(
    async (m: MissionSummary) => {
      const choice = routeFor(m);
      if (choice.kind === "observe") {
        // Best-effort register so the backend tails the log (harmless if known).
        try {
          await registerMission(m.mission_id);
        } catch {
          /* ignore — open the stream anyway */
        }
      }
      onSelect(choice);
    },
    [onSelect]
  );

  if (collapsed) {
    return (
      <div className="flex h-full w-10 flex-none flex-col items-center gap-2 border-r border-neutral-900 bg-neutral-950 py-2">
        <button
          onClick={onToggleCollapse}
          title="Expand missions"
          className="text-neutral-500 hover:text-neutral-200"
        >
          »
        </button>
        <button onClick={onNew} title="New mission" className="text-neutral-400 hover:text-sky-400">
          ＋
        </button>
        {needsHuman > 0 && (
          <span
            className="mt-1 inline-flex animate-pulse items-center rounded-full border border-amber-600/60 bg-amber-500/15 px-1 text-[10px] font-semibold text-amber-300"
            title={`${needsHuman} mission(s) need a human`}
          >
            🔔{needsHuman}
          </span>
        )}
      </div>
    );
  }

  return (
    <div className="flex h-full w-72 flex-none flex-col border-r border-neutral-900 bg-neutral-950">
      <div className="flex items-center justify-between border-b border-neutral-900 px-3 py-2.5">
        <div className="flex items-center gap-1.5">
          <span className="text-[9px] uppercase tracking-wide text-sky-500">Kun</span>
          <span className="text-xs font-semibold text-neutral-200">Missions</span>
          {needsHuman > 0 && (
            <span
              className="inline-flex animate-pulse items-center gap-0.5 rounded-full border border-amber-600/60 bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-amber-300"
              title={`${needsHuman} mission(s) need a human`}
            >
              🔔 {needsHuman}
            </span>
          )}
        </div>
        <button
          onClick={onToggleCollapse}
          title="Collapse"
          className="text-neutral-500 hover:text-neutral-200"
        >
          «
        </button>
      </div>

      <div className="flex flex-col gap-1.5 border-b border-neutral-900 px-3 py-2.5">
        <Button size="sm" onClick={onNew} className="w-full justify-start">
          ＋ New mission
        </Button>
        <div className="flex gap-1.5">
          <Button size="sm" variant="outline" onClick={onObserve} className="flex-1">
            Observe
          </Button>
          <Button size="sm" variant="outline" onClick={onReplay} className="flex-1">
            Replay
          </Button>
        </div>
      </div>

      <div className="flex items-center gap-1.5 px-3 py-2">
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search missions…"
          className="h-7 text-xs"
        />
        <button
          onClick={() => void load()}
          disabled={loading}
          title="Refresh"
          className={cn(
            "flex-none text-neutral-500 hover:text-neutral-200",
            loading && "animate-spin"
          )}
        >
          ↻
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-auto px-2 pb-3">
        <MissionHistory
          missions={filtered}
          activeId={activeMissionId}
          onOpen={open}
          loading={loading || missions == null}
        />
      </div>
    </div>
  );
});
