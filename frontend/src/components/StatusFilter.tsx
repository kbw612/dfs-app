import { STATUS_FILTER_GROUPS } from "../statusCodes";

interface StatusFilterProps {
  selected: Set<string>; // empty = no filter, show everything
  onChange: (next: Set<string>) => void;
}

export function StatusFilter({ selected, onChange }: StatusFilterProps) {
  function toggle(key: string) {
    const next = new Set(selected);
    if (next.has(key)) {
      next.delete(key);
    } else {
      next.add(key);
    }
    onChange(next);
  }

  return (
    <div className="status-filter">
      <span className="filter-label">Filter by status</span>
      <div className="chip-row">
        {STATUS_FILTER_GROUPS.map((g) => (
          <button
            key={g.key}
            type="button"
            className={`chip${selected.has(g.key) ? " selected" : ""}`}
            aria-pressed={selected.has(g.key)}
            title={g.codes.length > 1 ? g.codes.join(", ") : undefined}
            onClick={() => toggle(g.key)}
          >
            {g.label}
          </button>
        ))}
      </div>
    </div>
  );
}
