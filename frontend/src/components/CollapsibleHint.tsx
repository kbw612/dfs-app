import { useState } from "react";

interface CollapsibleHintProps {
  // One bullet per entry -- callers split their old single hint
  // paragraph into discrete points rather than passing one long string,
  // per an explicit "bullet points for readability" request.
  items: string[];
  // Defaults to "About this tab" -- every current caller (Game Logs,
  // Game Logs Against, Usage Bump Players) keeps the default; overridable
  // for a future caller that wants something more specific.
  title?: string;
  // Collapsed by default on every current caller, per an explicit
  // "collapsible by default" request -- exposed as a prop rather than
  // hardcoded in case a future caller wants the opposite.
  defaultExpanded?: boolean;
}

// A tab's own explanatory hint text as a collapsed-by-default toggle that
// expands into a bullet list, instead of a single always-visible
// paragraph -- so the help text doesn't eat vertical space every time the
// tab loads, and reads as a scannable list once opened. Reuses
// ContestResultsView's/OwnershipSummaryView's own expand/collapse header
// pattern (.ownership-summary-collapsible-header/-collapse-icon) rather
// than inventing a second visually-different toggle style.
export function CollapsibleHint({ items, title = "About this tab", defaultExpanded = false }: CollapsibleHintProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  return (
    <div className="collapsible-hint">
      <div
        className="collapsible-hint-header ownership-summary-collapsible-header"
        role="button"
        tabIndex={0}
        aria-expanded={expanded}
        onClick={() => setExpanded((v) => !v)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setExpanded((v) => !v);
          }
        }}
      >
        <span className="hint collapsible-hint-title">
          {title}
          <span className="ownership-summary-collapse-icon">{expanded ? "▴" : "▾"}</span>
        </span>
      </div>
      {expanded && (
        <ul className="hint collapsible-hint-list">
          {items.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
