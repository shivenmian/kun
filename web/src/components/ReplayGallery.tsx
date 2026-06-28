// Replay gallery — a small picker for the bundled reference trajectories.
//   - sample : loaded offline via replaySource() (no backend, {kind:"replay"}).
//   - the rest : registered with their repo-relative events_path, then observed
//     ({kind:"observe"}) — the backend resolves the path and tails it over SSE.
import { useState } from "react";
import { registerMission, type LaunchChoice } from "../lib/api";
import { Modal } from "./ui/primitives";

interface ReplayEntry {
  id: string;
  label: string;
  blurb: string;
  // when set, register this repo-relative path then observe; otherwise offline replay.
  eventsPath?: string;
}

const REPLAYS: ReplayEntry[] = [
  {
    id: "sample",
    label: "Fashion-MNIST sample",
    blurb: "The 78-event reference trajectory. Loads fully offline — no backend.",
  },
  {
    id: "probe_v4",
    label: "Autonomous research (real)",
    blurb: "Real Opus run: an autonomous LR range test that finds the optimum, overshoots, and self-corrects.",
    eventsPath: "examples/replays/autonomous_research.events.jsonl",
  },
  {
    id: "modded_nanogpt_run",
    label: "nanoGPT (synthesized)",
    blurb: "Hand-authored GPT speedrun trajectory — honesty-guarded as synthetic.",
    eventsPath: "examples/replays/nanogpt.events.jsonl",
  },
  {
    id: "agent_edit_real",
    label: "Agent-edit (real)",
    blurb: "Real capture of Kun's merged agent-edit patcher.",
    eventsPath: "examples/replays/agent_edit_real.events.jsonl",
  },
  {
    id: "mission_90b6668e",
    label: "Live steering (DoD #5)",
    blurb: "Verbatim live Mode-A capture with human steering.",
    eventsPath: "examples/replays/live_steering_dod5.events.jsonl",
  },
];

export function ReplayGallery({
  open,
  onClose,
  onSelect,
}: {
  open: boolean;
  onClose: () => void;
  onSelect: (c: LaunchChoice) => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);

  const choose = async (r: ReplayEntry) => {
    if (!r.eventsPath) {
      onSelect({ kind: "replay" }); // offline sample
      onClose();
      return;
    }
    setBusy(r.id);
    try {
      await registerMission(r.id, r.eventsPath);
    } catch {
      /* best-effort — open the stream anyway */
    }
    setBusy(null);
    onSelect({ kind: "observe", missionId: r.id });
    onClose();
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Load a replay"
      subtitle="Bundled reference trajectories. The sample runs offline; the rest tail their log."
    >
      <div className="flex flex-col gap-2">
        {REPLAYS.map((r) => (
          <button
            key={r.id}
            type="button"
            onClick={() => void choose(r)}
            disabled={busy != null}
            className="flex items-center justify-between gap-3 rounded-md border border-neutral-800 px-3 py-2.5 text-left hover:border-neutral-700 hover:bg-neutral-800/50 disabled:opacity-50"
          >
            <div className="min-w-0">
              <div className="text-sm font-medium text-neutral-100">{r.label}</div>
              <div className="truncate text-[11px] text-neutral-500">{r.blurb}</div>
            </div>
            <span className="flex-none text-xs text-sky-400">
              {busy === r.id ? "…" : r.eventsPath ? "Observe →" : "Replay →"}
            </span>
          </button>
        ))}
      </div>
    </Modal>
  );
}
