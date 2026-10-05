import { useEffect, useRef, useState } from "react";
import { fetchGamePreview, fetchGameRecaps } from "../api";
import type {
  GamePreviewGame,
  GamePreviewInjuryEntry,
  GamePreviewInjuryGroup,
  GamePreviewNarrativeSection,
  GamePreviewPaceTrend,
  GamePreviewPlayer,
  GamePreviewTagKind,
  GamePreviewTeamSide,
  GameRecapEntry,
  GameRecapWeekSnapshot,
  StatAverage,
} from "../types";
import { findTeamRecap } from "../types";
import { CollapsibleHint } from "./CollapsibleHint";
import { GameRecapModal } from "./GameRecapModal";
import { statTierClassName } from "./gameLogsShared";
import { STATUS_FILTER_GROUPS, isMultiWeekOut } from "../statusCodes";

// Shared by every PaceTrendCell -- which week's recap has been fetched
// (undefined = not tried, null = fetched, nothing scraped for that week)
// and the callback to open it in GameRecapModal, same "fetch once per
// week, reuse everywhere" pattern as Game Logs' own TeamRecapTable/
// recapsByWeek.
interface RecapLookup {
  recapsByWeek: Map<number, GameRecapWeekSnapshot | null>;
  onOpenRecap: (entry: GameRecapEntry, sourceUrl: string) => void;
}

// Same red/green volume-tier thresholds the backend's own
// tier_for_stat_value uses (see backend/services/game_logs/
// game_logs_engine.py) -- shown in the Team Volume section below so the
// person doesn't have to memorize or look up what "low"/"high" means for
// each stat. Keys match GamePreviewTeamSide.stat_summary's own field
// names.
const STAT_SUMMARY_THRESHOLDS: Record<string, [number, number]> = {
  rush_att: [21, 30],
  rush_yards: [85, 141],
  pass_att: [28, 38],
  pass_yds: [175, 261],
};

function formatStatNum(value: number | null): string {
  return value === null ? "-" : value.toFixed(1);
}

// Avg/median for one tiered stat (Rush Att/Rush Yds/Pass Att/Pass Yds) --
// each number independently colored by its own tier (see
// gameLogsShared.ts's statTierClassName), same red/green convention as
// Game Logs' own Team Summary (Avg / Median) section.
function TieredStatLine({ label, stat, thresholds }: { label: string; stat: StatAverage; thresholds: [number, number] }) {
  const [low, high] = thresholds;
  return (
    <li>
      {label}:{" "}
      <span className={statTierClassName(stat.average_tier)}>{formatStatNum(stat.average)} avg</span>
      {" / "}
      <span className={statTierClassName(stat.median_tier)}>{formatStatNum(stat.median)} median</span>
      <span className="game-preview-stat-summary-thresholds">
        {" "}
        (thresholds: ≤{low} low, ≥{high} high)
      </span>
    </li>
  );
}

// Plain avg/median for one untiered stat (Rec TD/Rush TD/Pass TD) -- no
// thresholds exist for these, so no coloring, per the person's own "just
// show the numbers" answer.
function PlainStatLine({ label, stat }: { label: string; stat: StatAverage }) {
  return (
    <li>
      {label}: {formatStatNum(stat.average)} avg / {formatStatNum(stat.median)} median
    </li>
  );
}

// Two independent badges, not a single mutually-exclusive pick -- a team
// can show "high" on Run Volume AND "low" on Pass Volume (or any other
// combination) at once; a single blue "Neither" pill shows only when
// NEITHER tier is set at all (both strictly in the normal range). Callers
// should only invoke this when stat_summary itself is known to exist
// (see TeamStatSummaryColumn below) -- runTier/passTier being null here
// is read as "genuinely normal," not "no data."
function volumeBadge(label: string, icon: string, tier: "low" | "high") {
  const cls = tier === "high" ? "game-preview-lean-high" : "game-preview-lean-low";
  return (
    <span className={`game-preview-lean-badge ${cls}`}>
      {icon} {label}
    </span>
  );
}

function leanBadges(runTier: "low" | "high" | null, passTier: "low" | "high" | null) {
  if (runTier === null && passTier === null) {
    return <span className="game-preview-lean-badge game-preview-lean-neither">Neither</span>;
  }
  return (
    <span className="game-preview-lean-badges">
      {runTier !== null && volumeBadge("Run", "🏃", runTier)}
      {passTier !== null && volumeBadge("Pass", "🎯", passTier)}
    </span>
  );
}

// One team's own column in the Team Volume (Avg / Median) row -- mirrors
// Game Logs' own Team Summary section's data (reused directly, see
// backend GamePreviewTeamSide.stat_summary's own docstring), with the
// same above/below-threshold coloring on Rush Att/Rush Yds/Pass Att/Pass
// Yds, the TD stats shown plainly, and Run/Pass Volume badges -- same
// "just like Ownership" badge treatment the person asked for, now with
// its own red (below threshold)/green (above threshold) coloring per
// side rather than one combined "leaning" pick.
function TeamStatSummaryColumn({ side }: { side: GamePreviewTeamSide }) {
  const s = side.stat_summary;
  return (
    <div className="game-preview-injuries-col">
      <h5 className="game-preview-injuries-col-team">
        {side.team} {s !== null && leanBadges(side.run_volume_tier, side.pass_volume_tier)}
      </h5>
      {s === null ? (
        <p className="hint">No recent stat lines for {side.team} yet.</p>
      ) : (
        <ul className="game-preview-stat-summary-list">
          <TieredStatLine label="Rush Att" stat={s.rush_att} thresholds={STAT_SUMMARY_THRESHOLDS.rush_att} />
          <TieredStatLine label="Rush Yds" stat={s.rush_yards} thresholds={STAT_SUMMARY_THRESHOLDS.rush_yards} />
          <TieredStatLine label="Pass Att" stat={s.pass_att} thresholds={STAT_SUMMARY_THRESHOLDS.pass_att} />
          <TieredStatLine label="Pass Yds" stat={s.pass_yds} thresholds={STAT_SUMMARY_THRESHOLDS.pass_yds} />
          <PlainStatLine label="Rush TD" stat={s.rush_td} />
          <PlainStatLine label="Pass TD" stat={s.pass_td} />
        </ul>
      )}
    </div>
  );
}

// season/week/platform/contest come from the shared header control (see
// App.tsx), same as every other weekly/platform/contest-scoped tab --
// `contest` narrows the Game filter chips below to that contest's own DK
// salary slate (see backend/api/game_preview/game_preview.py's own
// docstring), defaulting to showing every one of that contest's games
// ("All" selected) rather than any single one.
interface GamePreviewViewProps {
  season: number;
  week: number;
  platform: string;
  contest: string;
}

// How long to wait after the last keystroke in the "Weeks to show" input
// before refetching -- same debounce idea as DST/Off Trends' own field
// (this tab's own DST-matchup piece uses the same trailing-window concept).
const WINDOW_WEEKS_DEBOUNCE_MS = 800;

const TAG_LABELS: Record<GamePreviewTagKind, string> = {
  play: "Play",
  fade: "Fade",
  monitor: "Monitor",
  leverage: "Leverage",
  chalk: "Chalk",
};

// "WR1", "DST" (no depth known) -- same "position + depth suffix"
// convention as the Injury Report tab's own Pos column.
function formatPositionDepth(position: string, depth: number | null): string {
  return depth === null ? position : `${position}${depth}`;
}

// "yellow" -> "game-preview-weather-yellow" -- same sanitizing spirit as
// WeatherView's own colorClassName, so an unexpected color string from the
// scrape can't inject an arbitrary class name.
function weatherColorClassName(color: string): string {
  const safe = color.toLowerCase().replace(/[^a-z0-9-]/g, "");
  return `game-preview-weather-swatch-${safe || "unknown"}`;
}

function TeamPlayers({ side }: { side: GamePreviewTeamSide }) {
  if (side.players.length === 0) {
    return <p className="hint game-preview-no-players">No player-level signals for {side.team} this week.</p>;
  }
  return (
    <ul className="game-preview-player-list">
      {side.players.map((p: GamePreviewPlayer) => (
        <li key={`${p.team}-${p.position}-${p.name}`} className="game-preview-player-row">
          <div className="game-preview-player-name-row">
            <span className="game-preview-player-name">{p.name}</span>
            <span className="game-preview-player-position">{formatPositionDepth(p.position, p.depth)}</span>
          </div>
          <div className="game-preview-tag-row">
            {p.tags.map((t, i) => (
              <span key={i} className={`game-preview-tag game-preview-tag-${t.kind}`} title={t.reason}>
                {TAG_LABELS[t.kind]}
              </span>
            ))}
          </div>
          <ul className="game-preview-tag-reasons">
            {p.tags.map((t, i) => (
              <li key={i}>
                <strong>{TAG_LABELS[t.kind]}:</strong> {t.reason}
              </li>
            ))}
          </ul>
        </li>
      ))}
    </ul>
  );
}

// Same row-shading rule InjuryReportView.tsx's own injuryStatusRowClassName
// applies -- Doubtful or any code in the "O" filter group gets the same
// red background/bold-starred treatment as that tab's own grid, reusing
// its exact classes (.injury-report-row-out/-starred/-star-cell) rather
// than a separate game-preview-only copy, per an explicit "table format
// like Injury Report" request. A multi-week Out code (IR, SUS, PUP, etc. --
// see statusCodes.ts's isMultiWeekOut) gets the darker
// .injury-report-row-out-multi-week shade instead of plain -out, same
// "gone a while" vs "just this week" distinction Injury Report and Depth
// Charts both already make.
function injuryRowClassName(status: string, starred: boolean): string {
  const classes: string[] = [];
  const outCodes = STATUS_FILTER_GROUPS.find((g) => g.key === "O")!.codes;
  if (isMultiWeekOut(status)) {
    classes.push("injury-report-row-out-multi-week");
  } else if (status === "D" || outCodes.includes(status)) {
    classes.push("injury-report-row-out");
  }
  if (starred) classes.push("injury-report-row-starred");
  return classes.join(" ");
}

// A table per group, same shared grid classes as Injury Report's own
// player table -- deliberately no <thead> (tried without a header row per
// explicit request), since each group's own label above it already says
// what the columns are (position/depth, name, status).
function InjuryGroupTable({ group }: { group: GamePreviewInjuryGroup }) {
  return (
    <div className="game-preview-injury-group">
      <span className="game-preview-injury-group-label">{group.label}</span>
      <div className="player-pool-grid-wrap ownership-summary-grid-wrap">
        <table className="player-pool-grid injury-report-grid game-preview-injury-table">
          <tbody>
            {group.entries.map((entry: GamePreviewInjuryEntry, i) => (
              <tr key={i} className={injuryRowClassName(entry.status, entry.starred)}>
                <td className="injury-report-star-cell">{entry.starred ? "★" : ""}</td>
                <td>{formatPositionDepth(entry.position, entry.depth)}</td>
                <td>{entry.player}</td>
                <td>{entry.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function TeamSidePanel({ side }: { side: GamePreviewTeamSide }) {
  return (
    <div className="game-preview-team-panel">
      <h4>{side.team}</h4>
      {/* The per-side DST sacks/takeaways block used to render here, right
          above Injuries -- removed since the same numbers are already
          stated in the card's own "O vs D Line Matchup" narrative section
          above, so showing them again per-side was pure duplication. */}
      {/* Injury group tables (and the "Injuries" label itself) now live
          entirely under the card's own Injuries bullet in the top
          narrative list (see GameCard) -- both teams' tables side by side
          there, rather than repeated per-team under each abbreviation. */}
      <TeamPlayers side={side} />
    </div>
  );
}

// Matches game_preview_narrative.py's HIGH_OVER_UNDER_FLAG_LINE/
// LOW_OVER_UNDER_FLAG_LINE exactly -- these are the Ownership section's own
// leading flag bullet (same icon+label as the card header's own badge, see
// GameCard below), rendered as that same badge component instead of plain
// bullet text.
const HIGH_OVER_UNDER_FLAG_TEXT = "🔥 High O/U";
const LOW_OVER_UNDER_FLAG_TEXT = "❄️ Low O/U";
// Matches game_preview_narrative.py's _ownership_combined_line format
// exactly: "{icon? }Z.Z% projected ownership = {icon? }AWAY X.X% + {icon?
// }HOME Y.Y%" -- combined total leads, per-team breakdown follows. Each of
// the three numbers independently carries LOW_OWNERSHIP_ICON (📉) or
// HIGH_OWNERSHIP_ICON (📈) or neither, per that week's own top/bottom-third
// ranking (see compute_ownership_bands/classify_by_bands). Captures:
// combinedIcon, combinedPct, awayIcon, awayTeam, awayPct, homeIcon,
// homeTeam, homePct.
const OWNERSHIP_COMBINED_RE =
  /^(?:(📉|📈) )?([\d.]+)% projected ownership = (?:(📉|📈) )?(\S+) ([\d.]+)% \+ (?:(📉|📈) )?(\S+) ([\d.]+)%$/u;

// One badge per flagged number in the combined ownership line above --
// "Low Own"/"High Own" (cool-blue/warm-orange pills, same look as the
// High/Low O/U card badge) when this specific number (a team's own pct, or
// the game's own combined pct) was flagged; null (no badge) otherwise.
function ownershipIconBadge(icon: string | undefined) {
  if (icon === "📉") {
    return <span className="game-preview-low-own-badge">📉 Low Own</span>;
  }
  if (icon === "📈") {
    return <span className="game-preview-high-own-badge">📈 High Own</span>;
  }
  return null;
}

function renderNarrativeEntry(entry: string, key: number) {
  // The Vegas bullet's own High/Low O/U flag now leads that same bullet as
  // a space-separated prefix (see game_preview_narrative.py's
  // _vegas_section, e.g. "🔥 High O/U 49.5 O/U (...)") rather than standing
  // as its own separate bullet -- render the badge, then the rest of the
  // line, inside one <li>.
  if (entry.startsWith(`${HIGH_OVER_UNDER_FLAG_TEXT} `)) {
    return (
      <li key={key}>
        <span className="game-preview-high-ou-badge">{HIGH_OVER_UNDER_FLAG_TEXT}</span>{" "}
        {entry.slice(HIGH_OVER_UNDER_FLAG_TEXT.length + 1)}
      </li>
    );
  }
  if (entry.startsWith(`${LOW_OVER_UNDER_FLAG_TEXT} `)) {
    return (
      <li key={key}>
        <span className="game-preview-low-ou-badge">{LOW_OVER_UNDER_FLAG_TEXT}</span>{" "}
        {entry.slice(LOW_OVER_UNDER_FLAG_TEXT.length + 1)}
      </li>
    );
  }
  if (entry === HIGH_OVER_UNDER_FLAG_TEXT) {
    return (
      <li key={key}>
        <span className="game-preview-high-ou-badge">{HIGH_OVER_UNDER_FLAG_TEXT}</span>
      </li>
    );
  }
  if (entry === LOW_OVER_UNDER_FLAG_TEXT) {
    return (
      <li key={key}>
        <span className="game-preview-low-ou-badge">{LOW_OVER_UNDER_FLAG_TEXT}</span>
      </li>
    );
  }
  const ownershipMatch = entry.match(OWNERSHIP_COMBINED_RE);
  if (ownershipMatch) {
    const [, combinedIcon, combinedPct, awayIcon, awayTeam, awayPct, homeIcon, homeTeam, homePct] = ownershipMatch;
    return (
      <li key={key}>
        {ownershipIconBadge(combinedIcon)}
        {combinedPct}% projected ownership = {ownershipIconBadge(awayIcon)}
        {awayTeam} {awayPct}% + {ownershipIconBadge(homeIcon)}
        {homeTeam} {homePct}%
      </li>
    );
  }
  return <li key={key}>{entry}</li>;
}

// "8" -> "+8", "-8" -> "-8", "0" -> "+0" -- explicit sign on a delta so it
// always reads as a change rather than a plain number, matching the sign
// convention the narrative bullets already use for the same deltas.
function signedDelta(value: number): string {
  return value > 0 ? `+${value}` : `${value}`;
}

// Wraps a delta in a colored span -- green for a positive change, red for a
// negative one -- so a glance at the pace table shows direction without
// reading the sign character. Zero renders in the default (unstyled) color,
// matching signedDelta's own "+0" text which isn't really an increase.
function DeltaText({ value }: { value: number }) {
  const cls =
    value > 0 ? "game-preview-delta-positive" : value < 0 ? "game-preview-delta-negative" : undefined;
  return <span className={cls}>({signedDelta(value)})</span>;
}

function NarrativeSectionItem({
  section,
  paceSides,
  recaps,
}: {
  section: GamePreviewNarrativeSection;
  paceSides?: { away: GamePreviewTeamSide; home: GamePreviewTeamSide };
  recaps: RecapLookup;
}) {
  if (section.label === null) {
    // The Vegas O/U line (with the High/Low O/U badge, when flagged,
    // leading that same bullet -- see game_preview_narrative.py's
    // _vegas_section) is the one label-less section, rendered as its own
    // top-level bullet (no nested sublist) via the same renderNarrativeEntry
    // used for labeled sections, so the flag still gets its badge treatment
    // instead of showing as plain text.
    return <>{section.entries.map((entry, i) => renderNarrativeEntry(entry, i))}</>;
  }
  return (
    <li>
      <strong>{section.label}</strong>
      {section.entries.length > 0 && (
        <ul className="game-preview-narrative-sublist">
          {section.entries.map((entry, i) => renderNarrativeEntry(entry, i))}
        </ul>
      )}
      {/* The "Offensive Pace" section's own weeks-as-columns trend table --
          nested directly under this same heading (rather than as a
          separate bullet elsewhere in the card) since it's just the
          multi-week view of the same pass/run rate numbers the bullets
          above already summarize for the single most recent week. Team
          Volume (Avg / Median) nests right under it too -- same Rush/Pass
          volume concept as the pace numbers above it, just averaged/
          medianed over the window instead of shown per week. */}
      {paceSides && (
        <>
          <PaceTrendTable away={paceSides.away} home={paceSides.home} recaps={recaps} />
          <div className="game-preview-stat-summary-heading">Team Volume (Avg / Median)</div>
          <div className="game-preview-injuries-row">
            <TeamStatSummaryColumn side={paceSides.away} />
            <TeamStatSummaryColumn side={paceSides.home} />
          </div>
        </>
      )}
    </li>
  );
}

// Weeks-as-columns pace trend table -- one row per team, one column per
// played week (newest first, from each side's own pace_trend.trailing),
// sized by the "Weeks to show" input. Only rendered when at least one side
// has a pace trend at all (both null means neither team has a played week
// with any stat line yet -- week 1, or no weekly stats uploaded).
function paceTrendWeeks(away: GamePreviewPaceTrend | null, home: GamePreviewPaceTrend | null): number[] {
  const weeks = new Set<number>();
  for (const entry of away?.trailing ?? []) weeks.add(entry.week);
  for (const entry of home?.trailing ?? []) weeks.add(entry.week);
  return Array.from(weeks).sort((a, b) => b - a);
}

function PaceTrendCell({
  trend,
  week,
  team,
  recaps,
}: {
  trend: GamePreviewPaceTrend | null;
  week: number;
  team: string;
  recaps: RecapLookup;
}) {
  const entry = trend?.trailing.find((w) => w.week === week);
  if (!entry) return <span className="game-preview-pace-cell-empty">—</span>;
  // "@" when this team played away that week, "vs" when home -- falls back
  // to "vs" when opponent_location is null (no Schedule coverage), same as
  // opponent itself falling back to "—" in that case.
  const prefix = entry.opponent_location === "away" ? "@" : "vs";

  // Score + win/loss shading + recap link -- same source/lookup Game
  // Logs' own TeamRecapTable uses (findTeamRecap against a per-week
  // GameRecapWeekSnapshot), fetched once per distinct week across every
  // game's own pace trailing weeks (see GamePreviewView's own
  // recapsByWeek effect). undefined in the map = not fetched yet, null =
  // fetched, nothing scraped for that week -- both render as "—", same as
  // a week with no recap at all.
  const snapshot = recaps.recapsByWeek.get(week) ?? null;
  const recapEntry = snapshot ? findTeamRecap(snapshot, team) : null;
  const score = recapEntry ? (recapEntry.away_team === team ? recapEntry.away_team_score : recapEntry.home_team_score) : null;
  const oppScore = recapEntry
    ? recapEntry.away_team === team
      ? recapEntry.home_team_score
      : recapEntry.away_team_score
    : null;
  const scoreClass =
    score !== null && oppScore !== null
      ? score > oppScore
        ? "game-preview-pace-score-win"
        : score < oppScore
          ? "game-preview-pace-score-loss"
          : "game-preview-pace-score-tie"
      : undefined;

  return (
    <span className="game-preview-pace-cell">
      {/* Top row: score (color-coded win/loss), opponent, Recap link --
          all three side by side, per the person's own "30-36 color coded
          cell @ SF recap link" ordering, with a gap between each so they
          don't run together. */}
      <span className="game-preview-pace-cell-top">
        {score !== null && oppScore !== null ? (
          <span className={scoreClass}>
            {score}-{oppScore}
          </span>
        ) : (
          <span className="game-preview-pace-cell-empty">—</span>
        )}
        <span className="game-preview-pace-cell-opp">
          {prefix} {entry.opponent ?? "—"}
        </span>
        {recapEntry && snapshot && (
          <button
            type="button"
            className="team-recap-view-link"
            onClick={() => recaps.onOpenRecap(recapEntry, snapshot.source_url)}
          >
            Recap
          </button>
        )}
      </span>
      <span className="game-preview-pace-cell-plays">
        {entry.plays} plays{entry.plays_delta != null && <> <DeltaText value={entry.plays_delta} /></>}
      </span>
      <span className="game-preview-pace-cell-rate">
        {entry.pass_rate_pct != null ? (
          <>
            {entry.pass_rate_pct}% pass{entry.pass_rate_delta != null && <> <DeltaText value={entry.pass_rate_delta} /></>}
            {" / "}
            {entry.rush_rate_pct}% rush{entry.rush_rate_delta != null && <> <DeltaText value={entry.rush_rate_delta} /></>}
          </>
        ) : (
          "—"
        )}
      </span>
    </span>
  );
}

function PaceTrendTable({
  away,
  home,
  recaps,
}: {
  away: GamePreviewTeamSide;
  home: GamePreviewTeamSide;
  recaps: RecapLookup;
}) {
  const weeks = paceTrendWeeks(away.pace_trend, home.pace_trend);
  if (weeks.length === 0) return null;
  return (
    <table className="game-preview-pace-table">
      <thead>
        <tr>
          <th scope="col">Team</th>
          {weeks.map((w) => (
            <th key={w} scope="col">
              Week {w}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {[away, home].map((side) => (
          <tr key={side.team}>
            <th scope="row">{side.team}</th>
            {weeks.map((w) => (
              <td key={w}>
                <PaceTrendCell trend={side.pace_trend} week={w} team={side.team} recaps={recaps} />
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function GameCard({ game, recaps }: { game: GamePreviewGame; recaps: RecapLookup }) {
  return (
    <li className="game-preview-card">
      {/* The High/Low O/U badge used to also render here, top-center in the
          card header -- moved to live only in its own O/U bullet in the
          narrative list below (see HIGH_OVER_UNDER_FLAG_TEXT/
          LOW_OVER_UNDER_FLAG_TEXT handling in renderNarrativeEntry), so it's
          not shown twice. */}
      <div className="game-preview-card-header">
        <span className="game-preview-matchup">{game.label}</span>
        {game.vegas?.kickoff_label && <span className="game-preview-kickoff">{game.vegas.kickoff_label}</span>}
      </div>
      <ul className="game-preview-narrative-list">
        {game.narrative_sections.map((section, i) => (
          <NarrativeSectionItem
            key={i}
            section={section}
            paceSides={section.label === "Offensive Pace" ? { away: game.away, home: game.home } : undefined}
            recaps={recaps}
          />
        ))}
        {/* Weather comes first, once, with a colored swatch (matching the
            Weather tab's own color coding) rather than being folded into
            the narrative sections above or shown a second time. When
            there's no weather data at all for this game, show a green "No
            weather concerns" bar instead of omitting the bullet -- same
            "always show both sides" convention as Ownership, so the
            absence of a concern reads as a positive signal rather than
            missing data. The "Weather" label itself is the bolded lead-in
            (same convention as every other labeled narrative section), so
            the message text no longer repeats "Weather:" on top of it. */}
        <li>
          <span className="game-preview-weather-bullet">
            <strong>Weather</strong>
            <span
              className={`game-preview-weather-swatch ${
                game.weather ? weatherColorClassName(game.weather.color) : "game-preview-weather-swatch-green"
              }`}
              aria-hidden="true"
            />
            <span>{game.weather ? game.weather.note : "No weather concerns"}</span>
          </span>
        </li>
        {/* Injuries comes after Weather -- both teams' own injury group
            tables now nest directly under this one bullet (a two-column
            away/home row, same layout convention as .game-preview-sides
            below) instead of repeating under each team's own abbreviation
            in TeamSidePanel. The divider that used to sit above
            TeamSidePanel now sits below this row instead (see
            .game-preview-injuries-row in App.css), separating Injuries
            from the plain team panels (name + player tags) below. */}
        <li>
          <strong>Injuries</strong>
          <div className="game-preview-injuries-row">
            <div className="game-preview-injuries-col">
              <h5 className="game-preview-injuries-col-team">{game.away.team}</h5>
              {game.away.injury_groups.map((group) => (
                <InjuryGroupTable key={group.label} group={group} />
              ))}
            </div>
            <div className="game-preview-injuries-col">
              <h5 className="game-preview-injuries-col-team">{game.home.team}</h5>
              {game.home.injury_groups.map((group) => (
                <InjuryGroupTable key={group.label} group={group} />
              ))}
            </div>
          </div>
        </li>
      </ul>
      <div className="game-preview-sides">
        <TeamSidePanel side={game.away} />
        <TeamSidePanel side={game.home} />
      </div>
    </li>
  );
}

export function GamePreviewView({ season, week, platform, contest }: GamePreviewViewProps) {
  const [windowWeeksInput, setWindowWeeksInput] = useState("5");
  const [windowWeeks, setWindowWeeks] = useState(5);
  const windowDebounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [games, setGames] = useState<GamePreviewGame[] | null>(null);
  const [throughWeek, setThroughWeek] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Game filter chips -- defaults to null ("All", i.e. every game on this
  // contest's own slate, per this tab's own contest scoping), same
  // "All"-by-default convention as Game Logs' own Game filter.
  const [selectedGame, setSelectedGame] = useState<string | null>(null);

  // Game Recaps for the Pace Trend table's own Score/Recap columns -- same
  // "one fetch per distinct week, shared across every team/game" pattern
  // as Game Logs' own TeamRecapTable/recapsByWeek (GameLogsView.tsx).
  // undefined = not fetched yet, null = fetched, nothing scraped for that
  // week.
  const [recapsByWeek, setRecapsByWeek] = useState<Map<number, GameRecapWeekSnapshot | null>>(new Map());
  const [openRecap, setOpenRecap] = useState<{ entry: GameRecapEntry; sourceUrl: string } | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchGamePreview(season, week, windowWeeks, platform, contest)
      .then((result) => {
        setGames(result.games);
        setThroughWeek(result.through_week);
      })
      .catch((err) => {
        setGames(null);
        setThroughWeek(null);
        setError(err instanceof Error ? err.message : "Failed to load Game Preview");
      })
      .finally(() => setLoading(false));
  }, [season, week, windowWeeks, platform, contest]);

  // Fetches Game Recaps for every distinct week present across every
  // game's own away/home pace_trend.trailing -- a small, bounded number
  // of requests (the "Weeks to show" window), same as Game Logs' own
  // effect. Already-fetched weeks aren't re-requested on a re-render
  // caused by filter changes, only when `games` itself changes.
  useEffect(() => {
    const weeks = new Set<number>();
    for (const game of games ?? []) {
      for (const entry of game.away.pace_trend?.trailing ?? []) weeks.add(entry.week);
      for (const entry of game.home.pace_trend?.trailing ?? []) weeks.add(entry.week);
    }
    const toFetch = [...weeks].filter((w) => !recapsByWeek.has(w));
    if (toFetch.length === 0) return;
    let cancelled = false;
    Promise.all(
      toFetch.map((w) =>
        fetchGameRecaps(season, w)
          .then((snapshot): [number, GameRecapWeekSnapshot | null] => [w, snapshot])
          .catch((): [number, GameRecapWeekSnapshot | null] => [w, null])
      )
    ).then((results) => {
      if (cancelled) return;
      setRecapsByWeek((prev) => {
        const next = new Map(prev);
        for (const [w, snapshot] of results) next.set(w, snapshot);
        return next;
      });
    });
    return () => {
      cancelled = true;
    };
  }, [games, season, recapsByWeek]);

  useEffect(() => {
    // Reset back to "All" whenever the underlying game list changes out
    // from under a specific selection (season/week/contest switch) --
    // otherwise a stale game key could stay "selected" while matching
    // nothing.
    setSelectedGame(null);
  }, [season, week, contest]);

  useEffect(() => {
    const timer = windowDebounce;
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  function commitWindowWeeks(value: string) {
    const parsed = Number(value);
    if (Number.isFinite(parsed) && parsed > 0) {
      setWindowWeeks(Math.floor(parsed));
    } else {
      setWindowWeeksInput(String(windowWeeks));
    }
  }

  function handleWindowWeeksChange(value: string) {
    setWindowWeeksInput(value);
    if (windowDebounce.current) clearTimeout(windowDebounce.current);
    windowDebounce.current = setTimeout(() => {
      windowDebounce.current = null;
      commitWindowWeeks(value);
    }, WINDOW_WEEKS_DEBOUNCE_MS);
  }

  function handleWindowWeeksBlur() {
    if (windowDebounce.current) {
      clearTimeout(windowDebounce.current);
      windowDebounce.current = null;
    }
    commitWindowWeeks(windowWeeksInput);
  }

  const isNotFound = error !== null && error.includes("No Schedule file uploaded yet");
  const visibleGames = games === null ? null : selectedGame === null ? games : games.filter((g) => g.key === selectedGame);

  return (
    <>
      <CollapsibleHint
        items={[
          "One card per this week's own Schedule matchup (on this contest's own slate), combining Vegas/Weather/Team Factors/DST matchup context (Phase A) with per-player Play/Fade/Monitor/Leverage/Chalk tags (Phase B), an auto-generated bullet summary (Phase C), and each team's own injury summary (Phase D).",
          "Every bullet -- narrative, player tag, and injury summary -- is a fully rule-based, fixed-threshold check -- see the backend's own game_preview_player_tags.py/game_preview_narrative.py/game_preview_injuries.py docstrings for the exact rules -- not a manually-editable or model-generated summary.",
          `The DST/Offensive matchup piece reviews the trailing window of completed weeks through week ${week} - 1${
            throughWeek !== null ? ` = week ${throughWeek}` : ""
          }, going back "Weeks to show" weeks (currently ${windowWeeks}, default 5) -- same convention as DST/Off Trends' own window.`,
          "A player only appears at all if at least one signal fired for them this week (Repeat Performer/Breakout Watch trend, a target/touch/opportunity share swing, an injury-driven usage bump, or a low/high ownership projection) -- \"no signal, no row\", same as Breakout Watch/Repeat Performers.",
          "Each team's own Injuries section covers 4 groups: O-Line (depth 1-2), Defensive Front (defensive line + linebackers combined, depth 1-2), Defensive Backs (depth 1-2), and Skill Positions (QB/RB/WR/TE, depth 1-4). A group with nothing notable simply doesn't show. A starred player (Star Players tab) shows a gold star next to their name in whichever group they already qualify for, rather than a separate group of their own.",
        ]}
      />

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
            {(games ?? []).map((g) => (
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
        <label className="game-logs-lookback-field">
          Weeks to show (DST/Offensive matchups)
          <input
            type="number"
            min={1}
            max={17}
            value={windowWeeksInput}
            onChange={(e) => handleWindowWeeksChange(e.target.value)}
            onBlur={handleWindowWeeksBlur}
          />
        </label>
      </div>

      {loading && <p className="hint">Loading…</p>}
      {!loading && error && isNotFound && <p className="hint">{error}</p>}
      {!loading && error && !isNotFound && <p className="error">{error}</p>}

      {!loading && !error && visibleGames !== null && visibleGames.length === 0 && (
        <p className="hint">No games found for season {season} week {week}.</p>
      )}

      {!loading && !error && visibleGames !== null && visibleGames.length > 0 && (
        <ul className="game-preview-list">
          {visibleGames.map((game) => (
            <GameCard
              key={game.key}
              game={game}
              recaps={{ recapsByWeek, onOpenRecap: (entry, sourceUrl) => setOpenRecap({ entry, sourceUrl }) }}
            />
          ))}
        </ul>
      )}

      {openRecap && (
        <GameRecapModal entry={openRecap.entry} sourceUrl={openRecap.sourceUrl} onClose={() => setOpenRecap(null)} />
      )}
    </>
  );
}
