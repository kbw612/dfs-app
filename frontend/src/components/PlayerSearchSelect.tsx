import { useState } from "react";

// Search-to-select player filter -- used where the option list (every
// player at a position) is too long to lay out as a flat chip row the way
// team/game/salary-bucket filters do (see ChipMultiSelect). Typing narrows
// a dropdown of matching names; picking one adds it to the selected set as
// a removable chip and clears the search box so you can look up the next
// one.
interface PlayerSearchSelectProps {
  label: string;
  options: string[];
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
  maxMatches?: number;
}

export function PlayerSearchSelect({
  label,
  options,
  selected,
  onChange,
  maxMatches = 8,
}: PlayerSearchSelectProps) {
  const [query, setQuery] = useState("");

  const trimmed = query.trim().toLowerCase();
  const matches = trimmed
    ? options.filter((name) => !selected.has(name) && name.toLowerCase().includes(trimmed)).slice(0, maxMatches)
    : [];

  function selectPlayer(name: string) {
    const next = new Set(selected);
    next.add(name);
    onChange(next);
    setQuery("");
  }

  function removePlayer(name: string) {
    const next = new Set(selected);
    next.delete(name);
    onChange(next);
  }

  return (
    <div className="chip-filter player-search">
      <span className="filter-label">{label}</span>

      <div className="player-search-box">
        <input
          type="text"
          className="player-search-input"
          placeholder="Search players…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && matches.length > 0) {
              e.preventDefault();
              selectPlayer(matches[0]);
            } else if (e.key === "Escape") {
              setQuery("");
            }
          }}
        />
        {matches.length > 0 && (
          <ul className="player-search-dropdown">
            {matches.map((name) => (
              <li key={name}>
                <button type="button" className="player-search-option" onClick={() => selectPlayer(name)}>
                  {name}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {selected.size > 0 && (
        <div className="chip-row player-chip-row">
          {[...selected].sort().map((name) => (
            <span key={name} className="chip selected player-chip">
              {name}
              <button
                type="button"
                className="player-chip-remove"
                aria-label={`Remove ${name}`}
                onClick={() => removePlayer(name)}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
