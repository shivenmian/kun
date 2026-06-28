// Mission launcher / loader. Three ways in:
//   1. Load the static sample replay (works fully offline, no backend).
//   2. Connect to a live mission {id} (hydrate + SSE).
//   3. Observe an external mission {id} (CONTRACT §8.2: POST /missions/register -> SSE).
// Plus a minimal model-id field (just a text field, not a settings UI).
import { useState } from "react";
import { Button, Card, CardBody, Input } from "./ui/primitives";
import { registerMission } from "../lib/api";

export type LaunchChoice =
  | { kind: "replay" }
  | { kind: "live"; missionId: string }
  | { kind: "observe"; missionId: string };

export function MissionLauncher({ onLaunch }: { onLaunch: (c: LaunchChoice, model: string) => void }) {
  const [liveId, setLiveId] = useState("");
  const [observeId, setObserveId] = useState("mission_external_demo");
  const [model, setModel] = useState("claude-opus-4-8");
  const [note, setNote] = useState("");

  const observe = async () => {
    if (!observeId) return;
    setNote("Registering external mission…");
    try {
      const r = await registerMission(observeId);
      setNote(r.ok ? "Registered — opening live stream." : `register returned ${r.status} (opening stream anyway)`);
    } catch (e) {
      setNote(`register failed (${String(e)}) — opening stream anyway`);
    }
    onLaunch({ kind: "observe", missionId: observeId }, model);
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-neutral-950 p-6">
      <div className="w-full max-w-xl">
        <div className="mb-6 text-center">
          <h1 className="text-2xl font-bold text-neutral-50">Kun — Mission Cockpit</h1>
          <p className="mt-1 text-sm text-neutral-500">
            Mission control for autonomous ML research trajectories.
          </p>
        </div>

        <Card className="mb-4">
          <CardBody>
            <div className="mb-3 flex items-end gap-2">
              <div className="flex-1">
                <label className="mb-1 block text-[10px] uppercase tracking-wide text-neutral-500">
                  Model (LiteLLM id)
                </label>
                <Input value={model} onChange={(e) => setModel(e.target.value)} />
              </div>
            </div>
          </CardBody>
        </Card>

        <Card className="mb-3">
          <CardBody className="flex items-center justify-between">
            <div>
              <div className="text-sm font-semibold text-neutral-100">Load sample replay</div>
              <div className="text-xs text-neutral-500">
                The 78-event reference trajectory. No backend required.
              </div>
            </div>
            <Button onClick={() => onLaunch({ kind: "replay" }, model)}>Load replay</Button>
          </CardBody>
        </Card>

        <Card className="mb-3">
          <CardBody>
            <div className="mb-2 text-sm font-semibold text-neutral-100">Connect to live mission</div>
            <div className="flex gap-2">
              <Input
                placeholder="mission_id"
                value={liveId}
                onChange={(e) => setLiveId(e.target.value)}
              />
              <Button
                variant="outline"
                disabled={!liveId}
                onClick={() => onLaunch({ kind: "live", missionId: liveId }, model)}
              >
                Connect
              </Button>
            </div>
            <div className="mt-1 text-xs text-neutral-500">
              Hydrate via /api/missions/{"{id}"}/events then tail /stream (SSE).
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardBody>
            <div className="mb-2 text-sm font-semibold text-neutral-100">
              Observe external mission <span className="text-[10px] text-purple-400">(wedge proof)</span>
            </div>
            <div className="flex gap-2">
              <Input
                placeholder="external mission_id"
                value={observeId}
                onChange={(e) => setObserveId(e.target.value)}
              />
              <Button variant="outline" disabled={!observeId} onClick={observe}>
                Observe
              </Button>
            </div>
            <div className="mt-1 text-xs text-neutral-500">
              POST /api/missions/register, then open its SSE stream — renders a loop Kun never ran.
            </div>
            {note && <div className="mt-1 text-xs text-amber-300">{note}</div>}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
