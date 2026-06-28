// Stacked toast notifications (bottom-right). Info/danger/success auto-dismiss;
// the sticky approval toast stays until the gate is resolved (it has no timer and
// no dismiss affordance). Fed by useAlerts — purely presentational here.
import { useEffect } from "react";
import type { Alert, AlertTone } from "../state/useAlerts";
import { cn } from "../lib/utils";

const TONE: Record<AlertTone, string> = {
  info: "border-sky-700/60 bg-sky-950/80 text-sky-100",
  warn: "border-amber-700/60 bg-amber-950/80 text-amber-100",
  danger: "border-red-700/60 bg-red-950/80 text-red-100",
  success: "border-emerald-700/60 bg-emerald-950/80 text-emerald-100",
};

const AUTO_DISMISS_MS = 7000;

function ToastCard({ alert, onDismiss }: { alert: Alert; onDismiss: (id: string) => void }) {
  useEffect(() => {
    if (alert.sticky) return;
    const t = window.setTimeout(() => onDismiss(alert.id), AUTO_DISMISS_MS);
    return () => window.clearTimeout(t);
  }, [alert.id, alert.sticky, onDismiss]);

  return (
    <div
      className={cn(
        "pointer-events-auto flex items-start gap-2 rounded-lg border px-3 py-2 shadow-lg backdrop-blur",
        TONE[alert.tone]
      )}
    >
      <div className="min-w-0 flex-1">
        <div className="text-xs font-semibold">{alert.title}</div>
        {alert.detail && (
          <div className="mt-0.5 truncate text-[11px] opacity-80" title={alert.detail}>
            {alert.detail}
          </div>
        )}
      </div>
      {!alert.sticky && (
        <button
          onClick={() => onDismiss(alert.id)}
          className="flex-none text-sm leading-none opacity-60 hover:opacity-100"
          title="Dismiss"
        >
          ✕
        </button>
      )}
    </div>
  );
}

export function Toaster({
  alerts,
  onDismiss,
}: {
  alerts: Alert[];
  onDismiss: (id: string) => void;
}) {
  if (alerts.length === 0) return null;
  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-80 flex-col gap-2">
      {alerts.map((a) => (
        <ToastCard key={a.id} alert={a} onDismiss={onDismiss} />
      ))}
    </div>
  );
}
