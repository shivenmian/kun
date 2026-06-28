// Node-view triad (2/3): unified diff vs parent, rendered with react-diff-viewer.
// We receive the unified `diff` string from file_diff_created and split it into the
// old/new sides the viewer expects.
import ReactDiffViewer, { DiffMethod } from "react-diff-viewer-continued";
import type { Experiment } from "../types";

/** Parse a unified diff string into (oldText, newText) for the side-by-side viewer. */
function splitUnifiedDiff(diff: string): { oldText: string; newText: string } {
  const oldLines: string[] = [];
  const newLines: string[] = [];
  for (const line of diff.split("\n")) {
    if (line.startsWith("---") || line.startsWith("+++") || line.startsWith("@@")) continue;
    if (line.startsWith("-")) oldLines.push(line.slice(1));
    else if (line.startsWith("+")) newLines.push(line.slice(1));
    else {
      const ctx = line.startsWith(" ") ? line.slice(1) : line;
      oldLines.push(ctx);
      newLines.push(ctx);
    }
  }
  return { oldText: oldLines.join("\n"), newText: newLines.join("\n") };
}

export function DiffViewer({ exp }: { exp?: Experiment }) {
  if (!exp) return <div className="p-4 text-sm text-neutral-500">Select a node.</div>;
  if (!exp.diff)
    return (
      <div className="p-4 text-sm text-neutral-500">
        No diff recorded for {exp.id} (no config change captured).
      </div>
    );

  const { oldText, newText } = splitUnifiedDiff(exp.diff);
  return (
    <div className="overflow-auto p-1 text-xs">
      <ReactDiffViewer
        oldValue={oldText}
        newValue={newText}
        splitView
        compareMethod={DiffMethod.WORDS}
        useDarkTheme
        leftTitle="parent"
        rightTitle={exp.id}
        styles={{
          variables: {
            dark: {
              diffViewerBackground: "#0a0a0a",
              gutterBackground: "#171717",
              addedBackground: "#16341f",
              removedBackground: "#3a1717",
            },
          },
          contentText: { fontFamily: "ui-monospace, monospace", fontSize: "12px" },
        }}
      />
    </div>
  );
}
