import { STATUS_CODES } from "../statusCodes";

interface StatusFilterProps {
  selected: Set<string>; // empty = no filter, show everything
  onChange: (next: Set<string>) => void;
}

export function StatusFilter({ selected, onChange }: StatusFilterProps) {
  function toggle(code: string) {
    const next = new Set(selected);
    if (next.has(code)) {
      next.delete(code);
    } else {
      next.add(code);
    }
    onChange(next);
  }

  return (
    <div className="status-filter">
      <span className="filter-label">Filter by status</span>
      <div className="chip-row">
        {STATUS_CODES.map((s) => (
          <button
            key={s.code}
            type="button"
            className={`chip${selected.has(s.code) ? " selected" : ""}`}
            aria-pressed={selected.has(s.code)}
            title={s.description}
            onClick={() => toggle(s.code)}
          >
            {s.label ?? s.code}
          </button>
        ))}
      </div>
    </div>
  );
}
