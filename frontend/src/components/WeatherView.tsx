import { useCallback, useEffect, useState } from "react";
import { fetchWeather, scrapeWeather } from "../api";
import type { WeatherGame, WeatherSnapshot } from "../types";

interface WeatherViewProps {
  season: number;
  week: number;
}

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString();
}

// "yellow" -> "weather-note-yellow" -- lowercased/sanitized so an
// unexpected color string from the source site can't inject an arbitrary
// class name, while still passing through colors this app hasn't
// hardcoded a rule for (see backend/schemas/weather/weather.py's
// docstring on why `color` isn't a fixed enum).
function colorClassName(color: string): string {
  const safe = color.toLowerCase().replace(/[^a-z0-9-]/g, "");
  return `weather-note-${safe || "unknown"}`;
}

export function WeatherView({ season, week }: WeatherViewProps) {
  const [data, setData] = useState<WeatherSnapshot | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scraping, setScraping] = useState(false);
  const [scrapeMessage, setScrapeMessage] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchWeather(season, week)
      .then((result) => setData(result))
      .catch((err) => {
        setData(null);
        setError(err instanceof Error ? err.message : "Failed to load Weather");
      })
      .finally(() => setLoading(false));
  }, [season, week]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleScrape() {
    setScraping(true);
    setScrapeMessage(null);
    try {
      const result = await scrapeWeather(season, week);
      const gameCount = result.snapshot.games.length;
      setScrapeMessage(
        result.messages.length > 0
          ? `Retrieved ${gameCount} note${gameCount === 1 ? "" : "s"} (${result.messages.length} message${
              result.messages.length === 1 ? "" : "s"
            } -- see below).`
          : `Retrieved ${gameCount} note${gameCount === 1 ? "" : "s"}.`
      );
      setData(result.snapshot);
      setError(null);
    } catch (err) {
      setScrapeMessage(err instanceof Error ? err.message : "Failed to retrieve Weather");
    } finally {
      setScraping(false);
    }
  }

  const isNotFound = error !== null && error.includes("No Weather scraped yet");

  return (
    <section className="ownership-section">
      <div className="player-pool-game-environment-header">
        <h2>Weather</h2>
        <button type="button" disabled={scraping} onClick={handleScrape}>
          {scraping ? "Retrieving…" : "Retrieve Weather"}
        </button>
      </div>
      {scrapeMessage && <p className="hint">{scrapeMessage}</p>}

      {loading && <p className="hint">Loading…</p>}
      {!loading && error && isNotFound && (
        <p className="hint">
          No Weather scraped yet for season {season} week {week} -- click "Retrieve Weather" above.
        </p>
      )}
      {!loading && error && !isNotFound && <p className="error">{error}</p>}

      {!loading && !error && data && (
        <>
          <p className="hint vegas-lines-timestamps">Last Updated: {formatTimestamp(data.scraped_at)}</p>

          {data.games.length === 0 ? (
            <p className="hint">No notable-weather games in this scrape.</p>
          ) : (
            <ul className="ownership-player-list pivot-card-list vegas-lines-list">
              {data.games.map((game: WeatherGame, i: number) => (
                <li
                  key={game.game_key ?? `${game.away_name}-${game.home_name}-${i}`}
                  className={`ownership-pivot-group weather-note-card ${colorClassName(game.color)}`}
                >
                  <div className="weather-note-header">
                    <span className="vegas-lines-matchup">
                      {game.away_name} at {game.home_name}
                    </span>
                    {game.kickoff_label && <span className="vegas-lines-kickoff">{game.kickoff_label}</span>}
                  </div>
                  <p className="weather-note-body">{game.note}</p>
                  {(game.away_team === null || game.home_team === null) && (
                    <div className="hint">Team name(s) unresolved</div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
