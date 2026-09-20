import { useState } from "react";
import type { DepthChartRosterPlayer } from "../types";

interface PlayerNameAutocompleteProps {
  value: string;
  onChange: (value: string) => void;
  // Already scoped to whatever's relevant to this field by the caller --
  // e.g. one team's own roster for a Usage Bump Players row, so a
  // beneficiary can't accidentally be typo'd onto the wrong team.
  candidates: DepthChartRosterPlayer[];
  // Names to hide from the dropdown even if they'd otherwise match --
  // e.g. the trigger player themselves, or beneficiaries already picked
  // in this same list, so the same name can't be selected twice.
  excludeNames?: string[];
  placeholder?: string;
  className?: string;
}

// Generous, not tight -- `candidates` is already scoped to one team's own
// roster by the caller (rarely more than ~20-25 players across QB/RB/WR/
// TE/FB), so this should essentially never truncate it. A tight cap here
// previously cut a whole position group (e.g. every TE) out of the list
// on an empty query, since results were sliced in position-sorted order
// (QB, RB, TE, WR) before any text was typed -- 4 QBs + 4 RBs alone
// already filled an 8-item cap, leaving no room for TE or WR at all. The
// dropdown itself scrolls (see .player-name-autocomplete-list's own
// max-height), so a generous cap doesn't overwhelm the screen even for a
// team with a long roster.
const MAX_SUGGESTIONS = 50;

// Small, reusable "type a name, pick from a dropdown of real roster
// players" input -- built for UsageBumpPlayersView.tsx's trigger-player
// and beneficiary-player name fields, but not tied to that feature.
// Free text is always still allowed (the underlying value is just a
// plain string, same as the file format itself) -- this only *suggests*,
// it never validates or requires a match, since a name that briefly isn't
// on the latest depth-chart snapshot (a practice-squad call-up, a
// snapshot that hasn't been re-scraped yet) shouldn't block saving.
export function PlayerNameAutocomplete({
  value,
  onChange,
  candidates,
  excludeNames = [],
  placeholder,
  className,
}: PlayerNameAutocompleteProps) {
  const [open, setOpen] = useState(false);

  const excluded = new Set(excludeNames.map((name) => name.toLowerCase()));
  const query = value.trim().toLowerCase();
  const suggestions = candidates
    .filter((c) => !excluded.has(c.player.toLowerCase()))
    .filter((c) => query === "" || c.player.toLowerCase().includes(query))
    .slice(0, MAX_SUGGESTIONS);

  return (
    <div className="player-name-autocomplete">
      <input
        type="text"
        className={className}
        value={value}
        placeholder={placeholder}
        onChange={(e) => {
          onChange(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        // Delayed close (rather than closing immediately) so a click on a
        // suggestion below still registers -- backed up by the
        // onMouseDown preventDefault on each suggestion button, which
        // keeps focus in the input in the first place.
        onBlur={() => setTimeout(() => setOpen(false), 150)}
      />
      {open && suggestions.length > 0 && (
        <ul className="player-name-autocomplete-list">
          {suggestions.map((c) => (
            <li key={`${c.team}-${c.player}`}>
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  onChange(c.player);
                  setOpen(false);
                }}
              >
                {c.player}
                <span className="player-name-autocomplete-meta">
                  {c.position}
                  {c.depth_rank}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
