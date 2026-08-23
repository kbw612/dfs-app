import { useState } from "react";
import { triggerScrape } from "../api";

interface RetrieveButtonProps {
  // Called after a successful scrape so the parent can refresh the
  // snapshot list -- the new file won't show up in the picker otherwise.
  onScraped: () => void;
}

export function RetrieveButton({ onScraped }: RetrieveButtonProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastTeamCount, setLastTeamCount] = useState<number | null>(null);

  async function handleClick() {
    setLoading(true);
    setError(null);
    try {
      const result = await triggerScrape();
      setLastTeamCount(result.team_count);
      onScraped();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scrape failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="retrieve-button">
      <button onClick={handleClick} disabled={loading}>
        {loading ? "Scraping…" : "Retrieve depth chart"}
      </button>
      {error && <p className="error">{error}</p>}
      {!error && lastTeamCount !== null && (
        <p className="hint">Saved a new snapshot ({lastTeamCount} teams).</p>
      )}
    </div>
  );
}
