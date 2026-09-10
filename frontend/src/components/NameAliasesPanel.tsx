import { useEffect, useState } from "react";
import { fetchNameAliases, saveNameAliases } from "../api";
import type { NameAlias } from "../types";

// Settings' Name Aliases panel -- a small, global (not season/week/
// platform-scoped) editable list of alias -> canonical player-name pairs
// (e.g. "James Cook III" -> "James Cook"), applied by DK Players'
// "Update Week N Points" action whenever it matches names across the
// Salary File, the 4 weekly FantasyData stat files, and Contest
// Standings -- three independent exports that don't always spell a name
// the same way. Saving always replaces the whole list.
export function NameAliasesPanel() {
  const [aliases, setAliases] = useState<NameAlias[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    fetchNameAliases()
      .then((result) => setAliases(result.aliases))
      .catch(() => setAliases([]))
      .finally(() => setLoading(false));
  }, []);

  function updateRow(index: number, field: "alias" | "canonical", value: string) {
    setAliases((prev) => prev.map((row, i) => (i === index ? { ...row, [field]: value } : row)));
  }

  function removeRow(index: number) {
    setAliases((prev) => prev.filter((_, i) => i !== index));
  }

  function addRow() {
    setAliases((prev) => [...prev, { alias: "", canonical: "" }]);
  }

  async function handleSave() {
    setSaving(true);
    setMessage(null);
    try {
      // Drop any half-filled rows rather than saving a broken alias.
      const cleaned = aliases.filter((row) => row.alias.trim() && row.canonical.trim());
      const result = await saveNameAliases(cleaned);
      setAliases(result.aliases);
      setMessage("Saved");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Failed to save name aliases");
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <p className="hint">Loading…</p>;

  return (
    <div className="name-aliases-panel">
      {aliases.map((row, i) => (
        <div key={i} className="name-alias-row">
          <input
            type="text"
            placeholder="Alias (e.g. James Cook III)"
            value={row.alias}
            onChange={(e) => updateRow(i, "alias", e.target.value)}
          />
          <span className="name-alias-arrow">→</span>
          <input
            type="text"
            placeholder="Canonical name (e.g. James Cook)"
            value={row.canonical}
            onChange={(e) => updateRow(i, "canonical", e.target.value)}
          />
          <button type="button" onClick={() => removeRow(i)} aria-label={`Remove alias ${row.alias || i + 1}`}>
            ✕
          </button>
        </div>
      ))}
      <div className="name-aliases-actions">
        <button type="button" onClick={addRow}>
          + Add alias
        </button>
        <button type="button" className="player-pool-save-button" disabled={saving} onClick={handleSave}>
          {saving ? "Saving…" : "Save"}
        </button>
        {message && <span className="hint">{message}</span>}
      </div>
    </div>
  );
}
