// Observe modal — register an externally-produced mission log so the backend
// tails it, then open it read-only (CONTRACT §8.2). mission_id + optional
// repo-relative events_path → POST /missions/register → select {kind:"observe"}.
import { useState } from "react";
import { registerMission, type LaunchChoice } from "../lib/api";
import { Button, Input, Label, Modal } from "./ui/primitives";

export function ObserveModal({
  open,
  onClose,
  onObserve,
}: {
  open: boolean;
  onClose: () => void;
  onObserve: (c: LaunchChoice) => void;
}) {
  const [missionId, setMissionId] = useState("mission_external_demo");
  const [eventsPath, setEventsPath] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");

  const submit = async () => {
    if (!missionId.trim()) return;
    setBusy(true);
    setStatus("Registering external mission…");
    try {
      const r = await registerMission(missionId.trim(), eventsPath.trim() || undefined);
      setStatus(r.ok ? "Registered — opening stream." : `register returned ${r.status} (opening anyway)`);
    } catch (e) {
      setStatus(`register failed (${String(e)}) — opening anyway`);
    } finally {
      setBusy(false);
    }
    onObserve({ kind: "observe", missionId: missionId.trim() });
    onClose();
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Observe external mission"
      subtitle="Render a loop Kun never ran — registers the log, then tails it over SSE."
      footer={
        <>
          {status && <span className="mr-auto self-center text-xs text-amber-300">{status}</span>}
          <Button variant="outline" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={() => void submit()} disabled={busy || !missionId.trim()}>
            Observe
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <div>
          <Label>Mission id</Label>
          <Input
            value={missionId}
            onChange={(e) => setMissionId(e.target.value)}
            placeholder="mission_external_demo"
          />
        </div>
        <div>
          <Label>Events path (optional, repo-relative)</Label>
          <Input
            value={eventsPath}
            onChange={(e) => setEventsPath(e.target.value)}
            placeholder="defaults to runs/<mission_id>/events.jsonl"
          />
          <div className="mt-1 text-[11px] text-neutral-600">
            POST /api/missions/register → opens /stream. The backend resolves repo-relative paths.
          </div>
        </div>
      </div>
    </Modal>
  );
}
