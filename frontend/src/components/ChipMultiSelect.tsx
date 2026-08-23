// Generic multi-select chip row -- used by the Usage Bump Players page
// for its team, position, and depth filters (StatusFilter on the Compare
// page predates this and has its own status-specific label/title logic,
// but shares the same .chip/.chip-row CSS).
//
// By default leads with an "All" chip, selected whenever nothing else is
// -- clicking it clears the selection entirely, which is the only way to
// get back to "show everything" once you've picked individual options one
// at a time. Set showAllOption={false} for a closed set of options with
// no unbounded/unrestricted state (e.g. Position Depth, which is always
// capped to its own option list -- there's no "5th string and deeper"
// escape hatch).
interface ChipMultiSelectProps {
  label: string;
  options: string[];
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
  getTitle?: (option: string) => string | undefined;
  allLabel?: string;
  showAllOption?: boolean;
}

export function ChipMultiSelect({
  label,
  options,
  selected,
  onChange,
  getTitle,
  allLabel = "All",
  showAllOption = true,
}: ChipMultiSelectProps) {
  function toggle(option: string) {
    const next = new Set(selected);
    if (next.has(option)) {
      next.delete(option);
    } else {
      next.add(option);
    }
    onChange(next);
  }

  return (
    <div className="chip-filter">
      <span className="filter-label">{label}</span>
      <div className="chip-row">
        {showAllOption && (
          <button
            type="button"
            className={`chip${selected.size === 0 ? " selected" : ""}`}
            aria-pressed={selected.size === 0}
            onClick={() => onChange(new Set())}
          >
            {allLabel}
          </button>
        )}
        {options.map((option) => (
          <button
            key={option}
            type="button"
            className={`chip${selected.has(option) ? " selected" : ""}`}
            aria-pressed={selected.has(option)}
            title={getTitle?.(option)}
            onClick={() => toggle(option)}
          >
            {option}
          </button>
        ))}
      </div>
    </div>
  );
}
