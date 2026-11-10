import { useState } from "react";

// "Hide RB/WR/TE owned below (%)" -- the <1% ownership filter's cutoff for
// one tab. Defaults to 1 (see backend/services/ownership/under_one.py); 0
// shows everyone. QBs and DSTs are never hidden. Applies on Enter or when the
// box loses focus; an invalid entry reverts to the last good value.
export function HideBelowField({ value, onChange }: { value: number; onChange: (next: number) => void }) {
  const [text, setText] = useState(String(value));

  function commit() {
    const parsed = Number(text);
    if (text.trim() !== "" && Number.isFinite(parsed) && parsed >= 0 && parsed <= 100) {
      onChange(parsed);
    } else {
      setText(String(value));
    }
  }

  return (
    <label className="game-logs-lookback-field">
      Hide RB/WR/TE owned below (%)
      <input
        type="text"
        inputMode="decimal"
        className="lp-chalk-input"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") commit();
        }}
      />
    </label>
  );
}
