// Resizable-panel chrome for the cockpit shell. Thin wrappers around
// react-resizable-panels so every workspace region is horizontally/vertically
// resizable AND collapsible — without rewriting the panels themselves.
//
// - ResizeHandle: a subtle, theme-matched drag bar (highlights on hover/drag).
// - usePanelCollapse: tracks a panel's collapsed state from its restored size
//   (works with autoSaveId persistence) + exposes an imperative toggle.
// - PanelCollapseButton: the chevron/✕ control dropped into a card header.
// - CollapsedStub: the always-visible slim re-open affordance shown in place of
//   a panel's body once it collapses (orientation follows the group direction).
// - PanelShell: Card chrome (header + scroll body) that swaps to CollapsedStub
//   when collapsed — used by the inline graph/node/memory/event cards.
import * as React from "react";
import { PanelResizeHandle, type ImperativePanelHandle } from "react-resizable-panels";
import { Card, CardHeader, CardTitle } from "./primitives";
import { cn } from "../../lib/utils";

type Direction = "horizontal" | "vertical";

/** A panel collapses when a parent PanelGroup lays it out horizontally; a
 *  collapse in a vertical group shrinks its height. The stub orients opposite. */
export function ResizeHandle({
  direction,
  className,
}: {
  direction: Direction;
  className?: string;
}) {
  const isH = direction === "horizontal";
  return (
    <PanelResizeHandle
      className={cn(
        "group relative flex flex-none items-center justify-center bg-neutral-900 transition-colors",
        "data-[resize-handle-state=hover]:bg-sky-700/40 data-[resize-handle-state=drag]:bg-sky-600/60",
        isH ? "w-1.5 cursor-col-resize" : "h-1.5 cursor-row-resize",
        className
      )}
    >
      {/* a faint grip line, brighter on hover/drag */}
      <span
        className={cn(
          "rounded-full bg-neutral-700 transition-colors group-hover:bg-sky-400",
          isH ? "h-8 w-0.5" : "h-0.5 w-8"
        )}
      />
    </PanelResizeHandle>
  );
}

/** Track collapsed state off the restored size so it survives reloads (autoSaveId). */
export function usePanelCollapse(collapsedSize: number) {
  const ref = React.useRef<ImperativePanelHandle>(null);
  const [collapsed, setCollapsed] = React.useState(false);
  const onResize = React.useCallback(
    (size: number) => setCollapsed(size <= collapsedSize + 0.5),
    [collapsedSize]
  );
  const toggle = React.useCallback(() => {
    const p = ref.current;
    if (!p) return;
    if (p.isCollapsed()) p.expand();
    else p.collapse();
  }, []);
  return { ref, collapsed, onResize, toggle };
}

/** Header chevron that collapses/expands the panel it belongs to. */
export function PanelCollapseButton({
  collapsed,
  onClick,
  direction,
}: {
  collapsed: boolean;
  onClick: () => void;
  direction: Direction;
}) {
  // chevron points toward where the panel will go when collapsed
  const icon = collapsed ? (direction === "horizontal" ? "›" : "⌄") : direction === "horizontal" ? "‹" : "⌃";
  return (
    <button
      onClick={onClick}
      title={collapsed ? "Expand panel" : "Collapse panel"}
      className="flex-none rounded px-1 text-neutral-500 transition-colors hover:bg-neutral-800 hover:text-neutral-200"
    >
      {icon}
    </button>
  );
}

/** Always-visible slim bar shown in place of a collapsed panel's body. */
export function CollapsedStub({
  title,
  direction,
  onExpand,
}: {
  title: React.ReactNode;
  /** group direction: horizontal => vertical stub strip; vertical => horizontal bar */
  direction: Direction;
  onExpand: () => void;
}) {
  if (direction === "horizontal") {
    // narrow vertical strip (panel got narrow): rotated title + reopen chevron
    return (
      <button
        onClick={onExpand}
        title="Expand panel"
        className="flex h-full w-full flex-col items-center gap-2 overflow-hidden rounded-lg border border-neutral-800 bg-neutral-900/60 py-2 text-neutral-400 transition-colors hover:bg-neutral-800/60 hover:text-neutral-200"
      >
        <span className="text-xs">›</span>
        <span
          className="whitespace-nowrap text-[10px] font-semibold uppercase tracking-wide"
          style={{ writingMode: "vertical-rl" }}
        >
          {title}
        </span>
      </button>
    );
  }
  // short horizontal bar (panel got short)
  return (
    <button
      onClick={onExpand}
      title="Expand panel"
      className="flex h-full w-full items-center gap-1.5 overflow-hidden rounded-lg border border-neutral-800 bg-neutral-900/60 px-3 text-neutral-400 transition-colors hover:bg-neutral-800/60 hover:text-neutral-200"
    >
      <span className="text-xs">⌄</span>
      <span className="truncate text-[10px] font-semibold uppercase tracking-wide">{title}</span>
    </button>
  );
}

/** Card chrome with a header collapse control; renders CollapsedStub when collapsed. */
export function PanelShell({
  title,
  meta,
  collapsed,
  direction,
  onToggle,
  bodyClassName,
  children,
}: {
  title: React.ReactNode;
  meta?: React.ReactNode;
  collapsed: boolean;
  direction: Direction;
  onToggle: () => void;
  bodyClassName?: string;
  children: React.ReactNode;
}) {
  if (collapsed) {
    return <CollapsedStub title={title} direction={direction} onExpand={onToggle} />;
  }
  return (
    <Card className="flex h-full min-h-0 flex-col">
      <CardHeader>
        <CardTitle className="truncate">{title}</CardTitle>
        <div className="flex items-center gap-2">
          {meta}
          <PanelCollapseButton collapsed={collapsed} onClick={onToggle} direction={direction} />
        </div>
      </CardHeader>
      <div className={cn("min-h-0 flex-1", bodyClassName)}>{children}</div>
    </Card>
  );
}
