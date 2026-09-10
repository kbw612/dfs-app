import { useEffect, useRef, useState } from "react";

interface HeaderInfoPopoverProps {
  // Each string renders as its own line in the popover -- callers pass
  // the scoring rule lines plus any supporting criteria as separate array
  // entries rather than one blob of text, so they read as a short list.
  lines: string[];
  // Defaults to "Scoring notes" (this component's original, header-only
  // use). Row-level callers (e.g. PlayerPoolView.tsx's per-game Vegas Line
  // popover) pass something more specific to that row's content.
  ariaLabel?: string;
  // The column's full, unabbreviated name (e.g. "Game Environment") --
  // shown bold at the top of the popover, above `lines`, for a header
  // whose own on-grid label has been shortened (e.g. "Game"/"Env" split
  // across two lines) to save column width. Omitted entirely (no title
  // row at all) for callers whose visible header text is already the
  // full name.
  title?: string;
}

// Small "ⓘ" icon next to a column header (Volume/Opportunities,
// Talent/Explosiveness -- see PlayerPoolView.tsx and SettingsView.tsx) --
// or, with a per-row `lines`/`ariaLabel`, next to a single grid cell (e.g.
// PlayerPoolView.tsx's Game Environment input) -- that toggles a compact
// popover with that column/cell's notes. Closes on a second click or a
// click anywhere outside it -- doesn't affect table layout since the
// popover is absolutely positioned over the grid rather than pushing rows
// down.
export function HeaderInfoPopover({ lines, ariaLabel = "Scoring notes", title }: HeaderInfoPopoverProps) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  return (
    <span className="header-info-wrap" ref={wrapRef}>
      <button
        type="button"
        className="header-info-icon"
        aria-label={ariaLabel}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        i
      </button>
      {open && (
        <div className="header-info-popover" role="tooltip">
          {title && <p className="header-info-popover-title">{title}</p>}
          {lines.map((line, i) => (
            <p key={i}>{line}</p>
          ))}
        </div>
      )}
    </span>
  );
}
