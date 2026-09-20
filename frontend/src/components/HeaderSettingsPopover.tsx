import { useEffect, useRef, useState } from "react";

// Only "DraftKings" has a real file format behind it today -- mirrors
// SettingsView.tsx's own PLATFORM_OPTIONS/CONTEST_OPTIONS exactly (that
// panel moved here, see this component's own docstring below).
const PLATFORM_OPTIONS = ["DraftKings"] as const;
const CONTEST_OPTIONS = ["Classic Main", "All Games"] as const;

interface HeaderSettingsPopoverProps {
  season: number;
  week: number;
  onSeasonChange: (season: number) => void;
  onWeekChange: (week: number) => void;
  platform: string;
  contest: string;
  onPlatformChange: (platform: string) => void;
  onContestChange: (contest: string) => void;
}

// Replaces the header's old read-only "Season 2026 · Week 2" text -- the
// trigger button shows the same at-a-glance readout (now with Platform/
// Contest appended too, since editing those used to require the Settings
// tab as well), and clicking it drops down the same Season/Week number
// inputs and Platform/Contest chip rows that used to live in Settings'
// own "Season & week"/"Platform & contest" panels (removed from
// SettingsView.tsx in favor of this single, always-reachable spot -- see
// that file's own history). Same click-outside-to-close pattern as
// HeaderInfoPopover, just triggered by a text button instead of an "i"
// icon and holding form inputs instead of static notes.
export function HeaderSettingsPopover({
  season,
  week,
  onSeasonChange,
  onWeekChange,
  platform,
  contest,
  onPlatformChange,
  onContestChange,
}: HeaderSettingsPopoverProps) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

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
    <div className="header-settings-wrap" ref={wrapRef}>
      <button
        type="button"
        className="header-settings-trigger"
        aria-expanded={open}
        aria-label="Change season, week, platform, or contest"
        onClick={() => setOpen((v) => !v)}
      >
        Season {season} · Week {week} · {platform} · {contest}
        <span className="header-settings-trigger-caret" aria-hidden="true">
          {open ? "▴" : "▾"}
        </span>
      </button>
      {open && (
        <div className="header-settings-popover" role="dialog" aria-label="Season, week, platform, and contest">
          <div className="header-settings-row">
            <label>
              Season
              <input
                type="number"
                value={season}
                onChange={(e) => onSeasonChange(Number(e.target.value) || season)}
              />
            </label>
            <label>
              Week
              <input
                type="number"
                min={1}
                max={18}
                value={week}
                onChange={(e) => onWeekChange(Number(e.target.value) || week)}
              />
            </label>
          </div>

          <div className="chip-filter">
            <span className="filter-label">Platform</span>
            <div className="chip-row">
              {PLATFORM_OPTIONS.map((p) => (
                <button
                  key={p}
                  type="button"
                  className={`chip${platform === p ? " selected" : ""}`}
                  aria-pressed={platform === p}
                  onClick={() => onPlatformChange(p)}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>

          <div className="chip-filter">
            <span className="filter-label">Contest</span>
            <div className="chip-row">
              {CONTEST_OPTIONS.map((c) => (
                <button
                  key={c}
                  type="button"
                  className={`chip${contest === c ? " selected" : ""}`}
                  aria-pressed={contest === c}
                  onClick={() => onContestChange(c)}
                >
                  {c}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
