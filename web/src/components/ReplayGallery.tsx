// Replay gallery — a picker for the bundled reference trajectories, DISCOVERED from
// disk (CONTRACT §5.3 GET /replays scans examples/replays/*.events.jsonl). Drop a new
// *.events.jsonl in and it shows up here automatically — nothing hardcoded.
//   - "sample" : loads offline via replaySource() ({kind:"replay"}, no backend needed).
//   - the rest : registered with their repo-relative events_path, then observed
//     ({kind:"observe"}) — the backend resolves the path and tails it over SSE.
// If the catalog can't be fetched (backend down), we still offer the offline sample.
import { useEffect, useState } from "react";
import { getReplays, registerMission, type LaunchChoice, type ReplaySummary } from "../lib/api";
import { Modal } from "./ui/primitives";
import { fmtMetric } from "../lib/utils";

const SAMPLE_FALLBACK: ReplaySummary = {
  id: "sample",
  name: "Fashion-MNIST sample",
  events_path: null, // offline
};

export function ReplayGallery({
  open,
  onClose,
  onSelect,
}: {
  open: boolean;
  onClose: () => void;
  onSelect: (c: LaunchChoice) => void;
}) {
  const [replays, setReplays] = useState<ReplaySummary[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  // Fetch the catalog each time the gallery opens (so newly-added files appear).
  useEffect(() => {
    if (!open) return;
    let alive = true;
    setReplays(null);
    getReplays().then((list) => {
      if (!alive) return;
      // Always ensure the offline sample is selectable, even if the backend is down.
      const hasSample = list.some((r) => r.id === "sample");
      setReplays(hasSample || list.length ? list : [SAMPLE_FALLBACK]);
    });
    return () => {
      alive = false;
    };
  }, [open]);

  const choose = async (r: ReplaySummary) => {
    // sample (or any entry without a path) loads offline.
    if (r.id === "sample" || !r.events_path) {
      onSelect({ kind: "replay" });
      onClose();
      return;
    }
    setBusy(r.id);
    try {
      await registerMission(r.id, r.events_path);
    } catch {
      /* best-effort — open the stream anyway */
    }
    setBusy(null);
    onSelect({ kind: "observe", missionId: r.id });
    onClose();
  };

  const list = replays ?? [];

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Load a replay"
      subtitle="Reference trajectories discovered from examples/replays/. The sample runs offline; the rest tail their log."
    >
      <div className="flex flex-col gap-2">
        {replays === null && (
          <div className="px-1 py-6 text-center text-xs text-neutral-500">Loading catalog…</div>
        )}
        {replays !== null && list.length === 0 && (
          <div className="px-1 py-6 text-center text-xs text-neutral-500">
            No replays found in examples/replays/.
          </div>
        )}
        {list.map((r) => {
          const offline = r.id === "sample" || !r.events_path;
          const best = r.best?.metric;
          return (
            <button
              key={r.id}
              type="button"
              onClick={() => void choose(r)}
              disabled={busy != null}
              className="flex items-center justify-between gap-3 rounded-md border border-neutral-800 px-3 py-2.5 text-left hover:border-neutral-700 hover:bg-neutral-800/50 disabled:opacity-50"
            >
              <div className="min-w-0">
                <div className="text-sm font-medium text-neutral-100">{r.name ?? r.id}</div>
                <div className="truncate text-[11px] text-neutral-500">
                  <span className="font-mono">{r.id}</span>
                  {typeof r.experiments_count === "number" && ` · ${r.experiments_count} exps`}
                  {best?.name && best?.value != null && ` · best ${best.name} ${fmtMetric(best.value)}`}
                  {offline && " · offline"}
                </div>
              </div>
              <span className="flex-none text-xs text-sky-400">
                {busy === r.id ? "…" : offline ? "Replay →" : "Observe →"}
              </span>
            </button>
          );
        })}
      </div>
    </Modal>
  );
}
