import { useEffect, useMemo, useRef, useState } from "react";
import type { KunEvent } from "./types";
import { reduceEvents } from "./state/eventReducer";
import { liveSource, replaySource, type DataSource } from "./lib/api";
import { TopbarStatus } from "./components/TopbarStatus";
import { TrajectoryGraph } from "./components/TrajectoryGraph";
import { ExperimentDetails } from "./components/ExperimentDetails";
import { DiffViewer } from "./components/DiffViewer";
import { Leaderboard } from "./components/Leaderboard";
import { CompareView } from "./components/CompareView";
import { MetricsChart } from "./components/MetricsChart";
import { ResearchMemoryPanel } from "./components/ResearchMemoryPanel";
import { EventStream } from "./components/EventStream";
import { ForkDialog } from "./components/ForkDialog";
import { MissionLauncher, type LaunchChoice } from "./components/MissionLauncher";
import { ApprovalGate } from "./components/ApprovalGate";
import { InstructBox } from "./components/InstructBox";
import { StopPauseControls } from "./components/StopPauseControls";
import { useMissionRuntime } from "./state/useMissionRuntime";
import type { PendingApproval } from "./lib/api";
import { Card, CardHeader, CardTitle, Button } from "./components/ui/primitives";
import { cn } from "./lib/utils";

type Tab = "details" | "diff" | "metrics" | "compare" | "leaderboard";

export default function App() {
  const [launched, setLaunched] = useState<LaunchChoice | null>(null);
  const [missionId, setMissionId] = useState<string | undefined>();
  const [events, setEvents] = useState<KunEvent[]>([]);
  const [selectedId, setSelectedId] = useState<string | undefined>();
  const [tab, setTab] = useState<Tab>("details");
  const [forkOpen, setForkOpen] = useState(false);
  const [conn, setConn] = useState<string>("");
  const [highlightConstraint, setHighlightConstraint] = useState<string | undefined>();
  const autoSelected = useRef(false);

  // Deep links for demos: ?replay  ·  ?live=<id>  ·  ?observe=<id>
  useEffect(() => {
    if (launched) return;
    const q = new URLSearchParams(window.location.search);
    if (q.has("replay")) setLaunched({ kind: "replay" });
    else if (q.get("live")) setLaunched({ kind: "live", missionId: q.get("live")! });
    else if (q.get("observe")) setLaunched({ kind: "observe", missionId: q.get("observe")! });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Subscribe to the chosen data source; everything flows into ONE reducer.
  useEffect(() => {
    if (!launched) return;
    setEvents([]);
    autoSelected.current = false;
    let src: DataSource;
    if (launched.kind === "replay") src = replaySource();
    else src = liveSource(launched.missionId); // live + observe share the hydrate+SSE path

    const dispose = src.start({
      onBatch: (evts) => setEvents(evts),
      onAppend: (evt) => {
        setEvents((prev) => [...prev, evt]);
        if (evt.type === "constraint_learned" || evt.type === "constraint_added") {
          const cid = (evt.payload as { constraint_id?: string })?.constraint_id;
          if (cid) {
            setHighlightConstraint(cid);
            window.setTimeout(() => setHighlightConstraint(undefined), 4000);
          }
        }
      },
      onOpen: () => setConn("connected"),
      onError: (e) => setConn(e),
    });
    return dispose;
  }, [launched]);

  const state = useMemo(() => reduceEvents(events), [events]);

  useEffect(() => {
    if (state.mission?.id) setMissionId(state.mission.id);
  }, [state.mission?.id]);

  // Auto-select the best node once data is present.
  useEffect(() => {
    if (autoSelected.current) return;
    if (state.experiments.length === 0) return;
    const target = state.bestExperimentId ?? state.experiments[state.experiments.length - 1].id;
    setSelectedId(target);
    autoSelected.current = true;
  }, [state.experiments.length, state.bestExperimentId]);

  const selected = selectedId ? state.experimentsById[selectedId] : undefined;
  const metricName = state.mission?.objective?.metric ?? "val_accuracy";

  // Live steering is only for a Mode-A live mission (?live=<id>), never replay/observe.
  const isLiveModeA = launched?.kind === "live";
  const { runtime, refresh: refreshRuntime } = useMissionRuntime(missionId, isLiveModeA);

  // Detect the pending approval to gate on. Primary source is GET /state (§9.1).
  // Defensive fallback: if approval is on but the backend didn't populate pending_approval,
  // derive the latest still-unresolved experiment_proposed from the event stream.
  const pendingApproval = useMemo<PendingApproval | null>(() => {
    if (!isLiveModeA) return null;
    if (runtime?.pending_approval) return runtime.pending_approval;
    if (!runtime?.approval_required) return null;
    const resolved = new Set<string>();
    let lastProposed: PendingApproval | null = null;
    for (const e of state.events) {
      if (e.type === "experiment_approved" || e.type === "experiment_rejected") {
        if (e.experiment_id) resolved.add(e.experiment_id);
      } else if (e.type === "experiment_proposed" && e.experiment_id) {
        const pl = (e.payload ?? {}) as Record<string, unknown>;
        lastProposed = {
          experiment_id: e.experiment_id,
          changes: pl.changes as Record<string, unknown> | undefined,
          operator: pl.operator as string | undefined,
          hypothesis: pl.hypothesis as string | undefined,
        };
      }
    }
    if (
      lastProposed &&
      !resolved.has(lastProposed.experiment_id) &&
      state.experimentsById[lastProposed.experiment_id]?.status === "proposed"
    ) {
      return lastProposed;
    }
    return null;
  }, [isLiveModeA, runtime, state.events, state.experimentsById]);

  const modeLabel = useMemo(() => {
    if (!launched) return "—";
    if (launched.kind === "replay") return "replay";
    if (launched.kind === "observe") return state.mode === "live" ? "B-observe / live" : "B-observe";
    return state.mode === "paused" ? "paused" : "A-live";
  }, [launched, state.mode]);

  if (!launched) {
    return (
      <MissionLauncher
        onLaunch={(c) => {
          setLaunched(c);
          if (c.kind !== "replay") setMissionId(c.missionId);
        }}
      />
    );
  }

  return (
    <div className="flex h-screen flex-col bg-neutral-950 text-neutral-200">
      <TopbarStatus
        state={state}
        selected={selected}
        modeLabel={modeLabel}
        runState={isLiveModeA ? runtime?.run_state : undefined}
      />

      <div className="flex items-center gap-2 border-b border-neutral-900 bg-neutral-950 px-4 py-1.5 text-xs">
        <Button size="sm" variant="ghost" onClick={() => setLaunched(null)}>
          ← Missions
        </Button>
        <span className="text-neutral-600">|</span>
        <span className="text-neutral-500">
          {launched.kind} {missionId ? `· ${missionId}` : ""} {conn && `· ${conn}`}
        </span>
        <div className="ml-auto flex items-center gap-2">
          {isLiveModeA && (
            <StopPauseControls
              missionId={missionId}
              runState={runtime?.run_state}
              onChanged={refreshRuntime}
            />
          )}
          <Button size="sm" variant="outline" onClick={() => setForkOpen(true)}>
            ⑂ Fork from {selected?.id ?? "node"}
          </Button>
        </div>
      </div>

      {/* live steering surface — Mode-A live only (CONTRACT §5.1 / §9) */}
      {isLiveModeA && pendingApproval && (
        <ApprovalGate
          missionId={missionId}
          pending={pendingApproval}
          onResolved={refreshRuntime}
        />
      )}

      {/* main 3-column workspace */}
      <div className="grid min-h-0 flex-1 grid-cols-12 gap-2 p-2">
        {/* left: trajectory graph */}
        <Card className="col-span-5 flex min-h-0 flex-col">
          <CardHeader>
            <CardTitle>Trajectory Graph</CardTitle>
            <span className="text-[10px] text-neutral-500">
              {state.experiments.length} nodes · badged by operator · colored by status
            </span>
          </CardHeader>
          <div className="min-h-0 flex-1">
            <TrajectoryGraph state={state} selectedId={selectedId} onSelect={setSelectedId} />
          </div>
        </Card>

        {/* center: node view triad + metrics */}
        <Card className="col-span-4 flex min-h-0 flex-col">
          <CardHeader>
            <CardTitle>Node View</CardTitle>
            <div className="flex gap-1">
              {(["details", "diff", "metrics", "compare", "leaderboard"] as Tab[]).map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className={cn(
                    "rounded px-2 py-0.5 text-[11px] capitalize",
                    tab === t
                      ? "bg-sky-600 text-white"
                      : "text-neutral-400 hover:bg-neutral-800"
                  )}
                >
                  {t}
                </button>
              ))}
            </div>
          </CardHeader>
          <div className="min-h-0 flex-1 overflow-auto">
            {tab === "details" && <ExperimentDetails exp={selected} />}
            {tab === "diff" && <DiffViewer exp={selected} />}
            {tab === "metrics" && <MetricsChart exp={selected} metricName={metricName} />}
            {tab === "compare" && (
              <CompareView state={state} selectedId={selectedId} onSelect={setSelectedId} />
            )}
            {tab === "leaderboard" && (
              <Leaderboard state={state} selectedId={selectedId} onSelect={setSelectedId} />
            )}
          </div>
        </Card>

        {/* right: research memory (hero) + event stream */}
        <div className="col-span-3 flex min-h-0 flex-col gap-2">
          <Card className="flex min-h-0 flex-[3] flex-col">
            <CardHeader>
              <CardTitle>🧠 Research Memory</CardTitle>
              <span className="text-[10px] text-neutral-500">{state.constraints.length} constraints</span>
            </CardHeader>
            <div className="min-h-0 flex-1 overflow-auto">
              <ResearchMemoryPanel
                constraints={state.constraints}
                highlightId={highlightConstraint}
                onSelectExperiment={setSelectedId}
              />
            </div>
          </Card>
          {isLiveModeA && (
            <Card className="flex flex-none flex-col">
              <CardHeader>
                <CardTitle>✍ Instruct</CardTitle>
                <span className="text-[10px] text-neutral-500">mid-run guidance</span>
              </CardHeader>
              <div className="overflow-auto">
                <InstructBox missionId={missionId} onSent={refreshRuntime} />
              </div>
            </Card>
          )}
          <Card className="flex min-h-0 flex-[2] flex-col">
            <CardHeader>
              <CardTitle>Event Stream</CardTitle>
              <span className="text-[10px] text-neutral-500">{state.events.length}</span>
            </CardHeader>
            <div className="min-h-0 flex-1">
              <EventStream events={state.events} />
            </div>
          </Card>
        </div>
      </div>

      <ForkDialog
        missionId={missionId}
        parent={selected}
        open={forkOpen}
        onClose={() => setForkOpen(false)}
        executes={isLiveModeA}
      />
    </div>
  );
}
