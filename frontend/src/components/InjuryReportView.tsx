import { useEffect, useMemo, useState } from "react";
import { fetchInjuryReport } from "../api";
import { POSITION_FILTER_GROUPS, POSITION_FILTER_INDIVIDUAL, positionsForFilters } from "../positionFilters";
import { STATUS_FILTER_GROUPS, isMultiWeekOut, statusMatchesFilter } from "../statusCodes";
import type { InjuryGameGroup, InjuryPlayerEntry, InjuryReportResult } from "../types";
import { ChipMultiSelect } from "./ChipMultiSelect";
import { CollapsibleHint } from "./CollapsibleHint";
import { StatusFilter } from "./StatusFilter";
import { StatusKey } from "./StatusKey";

// Row (not text) shading -- font stays plain black for every status per an
// explicit "keep the font color black" request; the signal now lives in the
// row's own background instead. Doubtful and every "Out" code (see the "O"
// filter group's own codes list) shade red (seriously in doubt or gone
// entirely) regardless of star status -- except a multi-week Out code (IR,
// SUS, PUP, etc. -- see statusCodes.ts's isMultiWeekOut), which shades a
// visibly darker red than plain "O"/Doubtful, since those mean gone for
// several weeks rather than just this one. Questionable is different: the
// gold shade only shows up for a STARRED Questionable player -- it's the
// same gold the star icon itself already is, so it reads as "this starred
// player is a bit banged up" rather than a general severity color; a
// non-starred Questionable player gets no background at all, per an
// explicit "remove yellow background for non-star questionable players"
// request. The star icon itself (.injury-report-star-cell) always renders
// gold regardless of which row shade is active, so an Out-and-starred row
// still shows a gold star against its red background.
function injuryStatusRowClassName(status: string | null, starred: boolean): string {
  if (status === null) return "";
  if (status === "Q") return starred ? "injury-report-row-questionable" : "";
  if (isMultiWeekOut(status)) return "injury-report-row-out-multi-week";
  const outCodes = STATUS_FILTER_GROUPS.find((g) => g.key === "O")!.codes;
  if (status === "D" || outCodes.includes(status)) return "injury-report-row-out";
  return "";
}

// "Position Depth" == the player's own rank within their position group,
// same fixed model as Usage Bump Players' own filter of the same name (see
// UsageBumpView.tsx) -- a hard cap, not a dynamic range like the Compare
// tab's depth filter, so 5th-string-and-deeper never shows regardless of
// which of these four are checked. Defaults to 1+2 (starters and immediate
// backups) rather than all four.
const POSITION_DEPTHS = ["1", "2", "3", "4"];

// Position Group and Position are two independent multi-select chip rows
// (rather than one merged list) so a broad group and a specific position
// can be combined -- e.g. "Defensive" group plus "Kickers" individual.
// Their selections are unioned into one set of raw position codes via
// positionsForFilters.
const POSITION_GROUP_LABELS = POSITION_FILTER_GROUPS.map((f) => f.label);
const POSITION_INDIVIDUAL_LABELS = POSITION_FILTER_INDIVIDUAL.map((f) => f.label);

// season/week/contest come from the shared header control (see App.tsx),
// same as Game Logs -- `contest` narrows the report to that contest's own
// teams (see backend/api/injury_report/latest.py), covering the "contest
// games or all games" filter without a second, tab-local toggle.
// refreshSignal is bumped by App whenever a new depth-chart snapshot is
// retrieved (from any tab), same pattern as DepthChartsView -- this report
// is only ever as fresh as the latest depth-chart scrape.
interface InjuryReportViewProps {
  season: number;
  week: number;
  contest: string;
  refreshSignal: number;
}

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString();
}

type StarFilter = "star" | "noStar" | null;

// Splits a game's own label back into its two team codes, in the same
// away/home (or, for the rare fallback label, alphabetical) order the
// backend already chose -- so the left/right column order matches the
// "AWAY @ HOME" reading of the label above them, rather than re-deriving
// it (or falling back to game.teams' own always-alphabetical order, which
// would silently disagree with the label for a home team that sorts first).
function labelTeamOrder(game: InjuryGameGroup): [string, string] {
  if (game.label.includes(" @ ")) {
    const [away, home] = game.label.split(" @ ");
    return [away, home];
  }
  if (game.label.includes(" vs ")) {
    const [a, b] = game.label.split(" vs ");
    return [a, b];
  }
  return [game.teams[0], game.teams[1]];
}

export function InjuryReportView({ season, week, contest, refreshSignal }: InjuryReportViewProps) {
  const [data, setData] = useState<InjuryReportResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Single-select, like Game Logs' own Game chip -- null = "All".
  const [selectedGame, setSelectedGame] = useState<string | null>(null);
  const [positionGroupFilter, setPositionGroupFilter] = useState<Set<string>>(new Set());
  const [positionIndividualFilter, setPositionIndividualFilter] = useState<Set<string>>(new Set());
  const [depthFilter, setDepthFilter] = useState<Set<string>>(new Set(["1", "2"]));
  const [statusFilter, setStatusFilter] = useState<Set<string>>(new Set());
  // Two mutually-exclusive chips, like the Team chip on Depth Charts --
  // clicking the already-selected one (or neither) shows everyone.
  const [starFilter, setStarFilter] = useState<StarFilter>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchInjuryReport(season, week, contest)
      .then((result) => setData(result))
      .catch((err) => {
        setData(null);
        setError(err instanceof Error ? err.message : "Failed to load Injury Report");
      })
      .finally(() => setLoading(false));
  }, [season, week, contest, refreshSignal]);

  // Union of both position chip rows -- empty selection on both means "All"
  // (null, no filtering), same convention as the old single-select dropdown.
  const positionMatch = useMemo(() => {
    const labels = [...positionGroupFilter, ...positionIndividualFilter];
    return labels.length === 0 ? null : positionsForFilters(labels);
  }, [positionGroupFilter, positionIndividualFilter]);

  const visibleGames = useMemo(() => {
    if (!data) return [];
    const games = selectedGame === null ? data.games : data.games.filter((g) => g.key === selectedGame);
    return games
      .map((g) => ({ ...g, players: filterPlayers(g.players) }))
      .filter((g) => g.players.length > 0);

    function filterPlayers(players: InjuryPlayerEntry[]): InjuryPlayerEntry[] {
      return players.filter((p) => {
        if (positionMatch !== null && !positionMatch.has(p.position)) return false;
        if (!POSITION_DEPTHS.includes(String(p.depth))) return false;
        if (depthFilter.size > 0 && !depthFilter.has(String(p.depth))) return false;
        if (statusFilter.size > 0 && !statusMatchesFilter(p.status, statusFilter)) return false;
        if (starFilter === "star" && !p.starred) return false;
        if (starFilter === "noStar" && p.starred) return false;
        return true;
      });
    }
  }, [data, selectedGame, positionMatch, depthFilter, statusFilter, starFilter]);

  const isNotFound = error !== null && error.includes("No depth chart scraped yet");

  return (
    <section className="ownership-section">
      <h2>Injury Report</h2>

      <CollapsibleHint
        items={[
          "Every player from the latest Depth Charts snapshot who currently carries a non-null status (Q/D/O/IR/etc.), grouped by this week's game matchup -- mirrors footballguys.com's own Weekly Injury Report.",
          "Retrieve a fresh depth chart from the Depth Charts tab -- this report always reads whatever that tab's own Retrieve button last saved.",
          "The gold star marks a player flagged in Star Players (toggle it from the Depth Charts tab) -- no star icon shows for anyone not flagged.",
          "A team on a bye this week, or with no Schedule row yet, doesn't appear here at all -- there's no game to group it under.",
        ]}
      />

      {loading && <p className="hint">Loading…</p>}
      {!loading && error && isNotFound && (
        <p className="hint">No depth chart scraped yet -- retrieve one from the Depth Charts tab first.</p>
      )}
      {!loading && error && !isNotFound && <p className="error">{error}</p>}

      {!loading && !error && data && (
        <>
          <p className="hint vegas-lines-timestamps">Depth chart last updated: {formatTimestamp(data.scraped_at)}</p>

          <div className="filters">
            <div className="chip-filter">
              <span className="filter-label">Game</span>
              <div className="chip-row">
                <button
                  type="button"
                  className={`chip${selectedGame === null ? " selected" : ""}`}
                  aria-pressed={selectedGame === null}
                  onClick={() => setSelectedGame(null)}
                >
                  All
                </button>
                {data.games.map((g) => (
                  <button
                    key={g.key}
                    type="button"
                    className={`chip${selectedGame === g.key ? " selected" : ""}`}
                    aria-pressed={selectedGame === g.key}
                    onClick={() => setSelectedGame((current) => (current === g.key ? null : g.key))}
                  >
                    {g.label}
                  </button>
                ))}
              </div>
            </div>
            <ChipMultiSelect
              label="Position Group"
              options={POSITION_GROUP_LABELS}
              selected={positionGroupFilter}
              onChange={setPositionGroupFilter}
            />
            <ChipMultiSelect
              label="Position"
              options={POSITION_INDIVIDUAL_LABELS}
              selected={positionIndividualFilter}
              onChange={setPositionIndividualFilter}
            />
            <ChipMultiSelect
              label="Position Depth"
              options={POSITION_DEPTHS}
              selected={depthFilter}
              onChange={setDepthFilter}
            />
            <StatusFilter selected={statusFilter} onChange={setStatusFilter} />
            <div className="chip-filter">
              <span className="filter-label">Star</span>
              <div className="chip-row">
                <button
                  type="button"
                  className={`chip${starFilter === null ? " selected" : ""}`}
                  aria-pressed={starFilter === null}
                  onClick={() => setStarFilter(null)}
                >
                  All
                </button>
                <button
                  type="button"
                  className={`chip${starFilter === "star" ? " selected" : ""}`}
                  aria-pressed={starFilter === "star"}
                  onClick={() => setStarFilter((cur) => (cur === "star" ? null : "star"))}
                >
                  ★ Star Players
                </button>
                <button
                  type="button"
                  className={`chip${starFilter === "noStar" ? " selected" : ""}`}
                  aria-pressed={starFilter === "noStar"}
                  onClick={() => setStarFilter((cur) => (cur === "noStar" ? null : "noStar"))}
                >
                  No Star
                </button>
              </div>
            </div>
            <StatusKey />
          </div>

          {visibleGames.length === 0 && <p className="hint">No injuries match the current filters.</p>}

          {visibleGames.map((game: InjuryGameGroup) => {
            const [leftTeam, rightTeam] = labelTeamOrder(game);
            const leftPlayers = game.players.filter((p) => p.team === leftTeam);
            const rightPlayers = game.players.filter((p) => p.team === rightTeam);
            return (
              <div className="depth-chart-team-card" key={game.key}>
                <h3>{game.label}</h3>
                <div className="injury-report-columns">
                  {[
                    { team: leftTeam, players: leftPlayers },
                    { team: rightTeam, players: rightPlayers },
                  ].map(({ team, players }) => (
                    <div className="injury-report-team-column" key={team}>
                      <div className="injury-report-team-band">{team}</div>
                      <div className="player-pool-grid-wrap ownership-summary-grid-wrap">
                        <table className="player-pool-grid injury-report-grid">
                          <thead>
                            <tr>
                              <th></th>
                              <th>Pos</th>
                              <th>Player</th>
                              <th>Status</th>
                            </tr>
                          </thead>
                          <tbody>
                            {/* Keyed by (team, position, player) -- (team, player) alone
                                collides for a player the depth chart lists at more than
                                one spot (e.g. a RB who's also the punt/kick returner, or
                                a backup filling multiple O-line slots). A duplicate key
                                there made React's reconciliation misbehave when the
                                Star filter shrank the list -- some of that player's rows
                                stuck around as stale DOM nodes instead of being removed. */}
                            {players.map((p) => (
                              <tr
                                key={`${p.team}-${p.position}-${p.player}`}
                                className={[
                                  injuryStatusRowClassName(p.status, p.starred),
                                  p.starred ? "injury-report-row-starred" : "",
                                ]
                                  .filter(Boolean)
                                  .join(" ")}
                              >
                                <td className="injury-report-star-cell">{p.starred ? "★" : ""}</td>
                                <td>
                                  {p.position}
                                  {p.depth}
                                </td>
                                <td>{p.player}</td>
                                <td>{p.status}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </>
      )}
    </section>
  );
}
