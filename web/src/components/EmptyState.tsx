// Homepage hero — shown in the cockpit center when no mission is selected. The
// rail still lists history; this is the "pick or create" call-to-action with the
// same three entry points the rail header exposes.
import { Button } from "./ui/primitives";

export function EmptyState({
  onNew,
  onObserve,
  onReplay,
}: {
  onNew: () => void;
  onObserve: () => void;
  onReplay: () => void;
}) {
  return (
    <div className="flex h-full flex-col items-center justify-center p-6 text-center">
      <div className="max-w-md">
        <div className="mb-2 text-[10px] uppercase tracking-[0.2em] text-sky-500">
          Kun · Mission Cockpit
        </div>
        <h1 className="text-2xl font-bold text-neutral-50">Select a mission, or create one</h1>
        <p className="mt-2 text-sm text-neutral-500">
          Mission control for autonomous ML research trajectories. Pick a mission from the rail to
          load it here, or start something new.
        </p>
        <div className="mt-6 flex flex-wrap items-center justify-center gap-2">
          <Button onClick={onNew}>＋ New mission</Button>
          <Button variant="outline" onClick={onObserve}>
            Observe external
          </Button>
          <Button variant="outline" onClick={onReplay}>
            Load replay
          </Button>
        </div>
      </div>
    </div>
  );
}
