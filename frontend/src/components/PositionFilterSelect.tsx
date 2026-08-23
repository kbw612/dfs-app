import { POSITION_FILTER_GROUPS, POSITION_FILTER_INDIVIDUAL } from "../positionFilters";

interface PositionFilterSelectProps {
  value: string; // "" = All, no filtering
  onChange: (value: string) => void;
}

export function PositionFilterSelect({ value, onChange }: PositionFilterSelectProps) {
  return (
    <div className="position-filter">
      <label>
        Filter by position
        <select value={value} onChange={(e) => onChange(e.target.value)}>
          <option value="">All</option>
          <optgroup label="Groups">
            {POSITION_FILTER_GROUPS.map((f) => (
              <option key={f.label} value={f.label}>
                {f.label}
              </option>
            ))}
          </optgroup>
          <optgroup label="Positions">
            {POSITION_FILTER_INDIVIDUAL.map((f) => (
              <option key={f.label} value={f.label}>
                {f.label}
              </option>
            ))}
          </optgroup>
        </select>
      </label>
    </div>
  );
}
