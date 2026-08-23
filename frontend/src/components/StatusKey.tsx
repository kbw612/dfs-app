import { useState } from "react";
import { STATUS_CODES } from "../statusCodes";

// Collapsed-by-default legend explaining what each status code means --
// separate from StatusFilter (which picks codes to filter by) so the two
// can be scanned/toggled independently.
export function StatusKey() {
  const [open, setOpen] = useState(false);

  return (
    <div className="status-key">
      <button
        type="button"
        className="status-key-toggle"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        Status key {open ? "▴" : "▾"}
      </button>
      {open && (
        <dl className="status-key-list">
          {STATUS_CODES.map((s) => (
            <div key={s.code} className="status-key-row">
              <dt>{s.code}</dt>
              <dd>{s.description}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}
