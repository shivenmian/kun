import { useEffect, useMemo, useRef, useState } from "react";
import type { KunEvent } from "./types";
import { reduceEvents } from "./state/eventReducer";
import { liveSource, replaySource, type DataSource, type LaunchChoice } from "./lib/api";
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
import { MissionNavigator, type MissionNavigatorHandle } from "./components/MissionNavigator";
import { NewMissionModal } from "./components/NewMissionModal";
import { ObserveModal } from "./components/ObserveModal";
import { ReplayGallery } from "./components/ReplayGallery";
import { EmptyState } from "./components/EmptyState";
import { ControlDeck } from "./components/ControlDeck";
import { ApprovalToggle } from "./components/ApprovalToggle";
import { Toaster } from "./components/Toaster";
import { useMissionRuntime } from "./state/useMissionRuntime";
import { useAlerts } from "./state/useAlerts";
import type { PendingApproval } from "./lib/api";
import { Button } from "./components/ui/primitives";
import {
  ResizeHandle,
  PanelShell,
  PanelCollapseButton,
  CollapsedStub,
  usePanelCollapse,
} from "./components/ui/panels";
import { Panel, PanelGroup, type ImperativePanelHandle } from "react-resizable-panels";
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

  // shell chrome
  const [navCollapsed, setNavCollapsed] = useState(false);
  const [newOpen, setNewOpen] = useState(false);
  const [observeOpen, setObserveOpen] = useState(false);
  const [replayOpen, setReplayOpen] = useState(false);
  const navRef = useRef<MissionNavigatorHandle>(null);

  // Resizable-panel collapse plumbing. The left rail's collapse is driven by its
  // Panel (single source of truth); navCollapsed just mirrors it so the navigator
  // renders its mini state + reopen affordance. Each workspace panel tracks its
  // own collapsed flag off its restored size (survives reload via autoSaveId).
  const railRef = useRef<ImperativePanelHandle>(null);
  const toggleRail = () => {
    const p = railRef.current;
    if (!p) return;
    if (p.isCollapsed()) p.expand();
    else p.collapse();
  };
  const graph = usePanelCollapse(3);
  const node = usePanelCollapse(3);
  const right = usePanelCollapse(3);
  const ctrl = usePanelCollapse(5);
  const memory = usePanelCollapse(5);
  const stream = usePanelCollapse(5);

  // Load a mission IN PLACE — the shell stays mounted; the data-source effect
  // below re-subscribes the single reducer to the new source.
  const selectMission = (c: LaunchChoice) => {
    setLaunched(c);
    setMissionId(c.kind === "replay" ? undefined : c.missionId);
  };
  const goHome = () => {
    setLaunched(null);
    setMissionId(undefined);
    setSelectedId(undefined);
  };

  // Deep links for demos: ?replay  ·  ?live=<id>  ·  ?observe=<id>
  useEffect(() => {
    if (launched) return;
    const q = new URLSearchParams(window.location.search);
    if (q.has("replay")) selectMission({ kind: "replay" });
    else if (q.get("live")) selectMission({ kind: "live", missionId: q.get("live")! });
    else if (q.get("observe")) selectMission({ kind: "observe", missionId: q.get("observe")! });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Subscribe to the chosen data source; everything flows into ONE reducer.
  useEffect(() => {
    if (!launched) {
      setEvents([]);
      return;
    }
    setEvents([]);
    setSelectedId(undefined);
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

  // Toasts + the topbar attention indicator, derived from the live stream + runtime.
  const { alerts, dismiss, attentionCount } = useAlerts(state.events, pendingApproval, isLiveModeA);

  const modeLabel = useMemo(() => {
    if (!launched) return "—";
    if (launched.kind === "replay") return "replay";
    if (launched.kind === "observe") return state.mode === "live" ? "B-observe / live" : "B-observe";
    return state.mode === "paused" ? "paused" : "A-live";
  }, [launched, state.mode]);

  return (
    <div className="h-screen overflow-hidden bg-neutral-950 text-neutral-200">
      {/* Outer shell split: resizable + collapsible left rail | main content. */}
      <PanelGroup direction="horizontal" autoSaveId="kun-shell" className="h-full">
        <Panel
          ref={railRef}
          id="rail"
          order={1}
          collapsible
          collapsedSize={3}
          minSize={12}
          maxSize={28}
          defaultSize={16}
          onResize={(s) => setNavCollapsed(s <= 3.5)}
          className="min-w-0"
        >
          <MissionNavigator
            ref={navRef}
            activeMissionId={launched ? missionId : undefined}
            collapsed={navCollapsed}
            onToggleCollapse={toggleRail}
            onSelect={(c) => {
              selectMission(c);
              navRef.current?.refresh();
            }}
            onNew={() => setNewOpen(true)}
            onObserve={() => setObserveOpen(true)}
            onReplay={() => setReplayOpen(true)}
          />
        </Panel>

        <ResizeHandle direction="horizontal" />

        <Panel id="main" order={2} minSize={40} className="min-w-0">
          <div className="flex h-full min-w-0 flex-col">
            {launched ? (
              <>
                <TopbarStatus
                  state={state}
                  selected={selected}
                  modeLabel={modeLabel}
                  runState={isLiveModeA ? runtime?.run_state : undefined}
                  attention={attentionCount}
                  controls={
                    isLiveModeA ? (
                      <ApprovalToggle
                        compact
                        missionId={missionId}
                        approvalRequired={runtime?.approval_required}
                        disabled={
                          runtime?.run_state === "stopped" || runtime?.run_state === "finished"
                        }
                        onChanged={refreshRuntime}
                      />
                    ) : undefined
                  }
                />

                <div className="flex items-center gap-2 border-b border-neutral-900 bg-neutral-950 px-4 py-1.5 text-xs">
                  <Button size="sm" variant="ghost" onClick={goHome}>
                    ⌂ Home
                  </Button>
                  <span className="text-neutral-600">|</span>
                  <span className="text-neutral-500">
                    {launched.kind} {missionId ? `· ${missionId}` : ""} {conn && `· ${conn}`}
                  </span>
                  <div className="ml-auto flex items-center gap-2">
                    {/* Live steering (incl. Fork) is grouped in the right-rail Control Deck.
                        For replay/observe, keep the record-only Fork affordance here. */}
                    {!isLiveModeA && (
                      <Button size="sm" variant="outline" onClick={() => setForkOpen(true)}>
                        ⑂ Fork from {selected?.id ?? "node"}
                      </Button>
                    )}
                  </div>
                </div>

                {/* resizable 3-column workspace (graph | node | right-stack) */}
                <div className="min-h-0 flex-1 p-2">
                  <PanelGroup direction="horizontal" autoSaveId="kun-workspace" className="h-full">
                    {/* left: trajectory graph */}
                    <Panel
                      ref={graph.ref}
                      id="graph"
                      order={1}
                      collapsible
                      collapsedSize={3}
                      minSize={20}
                      defaultSize={42}
                      onResize={graph.onResize}
                      className="min-w-0"
                    >
                      <PanelShell
                        title="Trajectory Graph"
                        direction="horizontal"
                        collapsed={graph.collapsed}
                        onToggle={graph.toggle}
                        meta={
                          <span className="text-[10px] text-neutral-500">
                            {state.experiments.length} nodes · badged by operator · colored by status
                          </span>
                        }
                      >
                        <TrajectoryGraph
                          state={state}
                          selectedId={selectedId}
                          onSelect={setSelectedId}
                        />
                      </PanelShell>
                    </Panel>

                    <ResizeHandle direction="horizontal" />

                    {/* center: node view triad + metrics */}
                    <Panel
                      ref={node.ref}
                      id="node"
                      order={2}
                      collapsible
                      collapsedSize={3}
                      minSize={18}
                      defaultSize={33}
                      onResize={node.onResize}
                      className="min-w-0"
                    >
                      <PanelShell
                        title="Node View"
                        direction="horizontal"
                        collapsed={node.collapsed}
                        onToggle={node.toggle}
                        bodyClassName="overflow-auto"
                        meta={
                          <div className="flex flex-wrap gap-1">
                            {(["details", "diff", "metrics", "compare", "leaderboard"] as Tab[]).map(
                              (t) => (
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
                              )
                            )}
                          </div>
                        }
                      >
                        {tab === "details" && <ExperimentDetails exp={selected} />}
                        {tab === "diff" && <DiffViewer exp={selected} />}
                        {tab === "metrics" && (
                          <MetricsChart exp={selected} metricName={metricName} />
                        )}
                        {tab === "compare" && (
                          <CompareView
                            state={state}
                            selectedId={selectedId}
                            onSelect={setSelectedId}
                          />
                        )}
                        {tab === "leaderboard" && (
                          <Leaderboard
                            state={state}
                            selectedId={selectedId}
                            onSelect={setSelectedId}
                          />
                        )}
                      </PanelShell>
                    </Panel>

                    <ResizeHandle direction="horizontal" />

                    {/* right: mission control (live) + research memory + event stream,
                        stacked in a vertical resizable sub-group */}
                    <Panel
                      ref={right.ref}
                      id="right"
                      order={3}
                      collapsible
                      collapsedSize={3}
                      minSize={15}
                      defaultSize={25}
                      onResize={right.onResize}
                      className="min-w-0"
                    >
                      {right.collapsed ? (
                        <CollapsedStub
                          title="Right Rail"
                          direction="horizontal"
                          onExpand={right.toggle}
                        />
                      ) : (
                        <PanelGroup
                          direction="vertical"
                          autoSaveId="kun-right"
                          className="h-full"
                        >
                          {isLiveModeA && (
                            <>
                              <Panel
                                ref={ctrl.ref}
                                id="control"
                                order={1}
                                collapsible
                                collapsedSize={5}
                                minSize={12}
                                defaultSize={26}
                                onResize={ctrl.onResize}
                                className="min-h-0"
                              >
                                {ctrl.collapsed ? (
                                  <CollapsedStub
                                    title="🛰 Mission Control"
                                    direction="vertical"
                                    onExpand={ctrl.toggle}
                                  />
                                ) : (
                                  <ControlDeck
                                    missionId={missionId}
                                    runtime={runtime}
                                    pendingApproval={pendingApproval}
                                    selectedId={selected?.id}
                                    onChanged={refreshRuntime}
                                    onFork={() => setForkOpen(true)}
                                    collapseControl={
                                      <PanelCollapseButton
                                        collapsed={false}
                                        onClick={ctrl.toggle}
                                        direction="vertical"
                                      />
                                    }
                                  />
                                )}
                              </Panel>
                              <ResizeHandle direction="vertical" />
                            </>
                          )}

                          <Panel
                            ref={memory.ref}
                            id="memory"
                            order={2}
                            collapsible
                            collapsedSize={5}
                            minSize={15}
                            defaultSize={isLiveModeA ? 44 : 60}
                            onResize={memory.onResize}
                            className="min-h-0"
                          >
                            <PanelShell
                              title="🧠 Research Memory"
                              direction="vertical"
                              collapsed={memory.collapsed}
                              onToggle={memory.toggle}
                              bodyClassName="overflow-auto"
                              meta={
                                <span className="text-[10px] text-neutral-500">
                                  {state.constraints.length} constraints
                                </span>
                              }
                            >
                              <ResearchMemoryPanel
                                constraints={state.constraints}
                                highlightId={highlightConstraint}
                                onSelectExperiment={setSelectedId}
                              />
                            </PanelShell>
                          </Panel>

                          <ResizeHandle direction="vertical" />

                          <Panel
                            ref={stream.ref}
                            id="events"
                            order={3}
                            collapsible
                            collapsedSize={5}
                            minSize={12}
                            defaultSize={isLiveModeA ? 30 : 40}
                            onResize={stream.onResize}
                            className="min-h-0"
                          >
                            <PanelShell
                              title="Event Stream"
                              direction="vertical"
                              collapsed={stream.collapsed}
                              onToggle={stream.toggle}
                              meta={
                                <span className="text-[10px] text-neutral-500">
                                  {state.events.length}
                                </span>
                              }
                            >
                              <EventStream events={state.events} />
                            </PanelShell>
                          </Panel>
                        </PanelGroup>
                      )}
                    </Panel>
                  </PanelGroup>
                </div>

                <ForkDialog
                  missionId={missionId}
                  parent={selected}
                  open={forkOpen}
                  onClose={() => setForkOpen(false)}
                  executes={isLiveModeA}
                />
              </>
            ) : (
              <EmptyState
                onNew={() => setNewOpen(true)}
                onObserve={() => setObserveOpen(true)}
                onReplay={() => setReplayOpen(true)}
              />
            )}
          </div>
        </Panel>
      </PanelGroup>

      {/* entry-point modals (shared by the rail header + the empty-state hero) */}
      <NewMissionModal
        open={newOpen}
        onClose={() => setNewOpen(false)}
        onCreated={(c) => {
          selectMission(c);
          navRef.current?.refresh();
        }}
      />
      <ObserveModal
        open={observeOpen}
        onClose={() => setObserveOpen(false)}
        onObserve={(c) => {
          selectMission(c);
          navRef.current?.refresh();
        }}
      />
      <ReplayGallery
        open={replayOpen}
        onClose={() => setReplayOpen(false)}
        onSelect={(c) => {
          selectMission(c);
          navRef.current?.refresh();
        }}
      />

      {/* live alerts/toasts — surfaces NaN→constraint, approval-needed, finished, new best */}
      <Toaster alerts={alerts} onDismiss={dismiss} />
    </div>
  );
}
