import { useState } from "react";
import type { OwnershipPlayer } from "../types";

// Shared by every ownership-data view (OwnershipView, SalaryBlocksView) --
// formatting/role helpers plus the two row-level building blocks
// (PlayerNameCell, PlayerRow) so the same fixed-width grid, truncation,
// and click-to-expand behavior looks identical everywhere a player list
// shows up, rather than drifting between views.

export function formatSalary(salary: number): string {
  return `$${salary.toLocaleString()}`;
}

// "-" when ownership isn't known yet (projections lag DK salaries by a
// few days -- see OwnershipPlayer.ownership_pct in types.ts) rather than
// crashing on null.toFixed() or silently showing "0.0%", which would read
// as a real (very low) ownership figure instead of "not loaded yet".
export function formatOwnershipPct(pct: number | null): string {
  return pct === null ? "-" : `${pct.toFixed(1)}%`;
}

// "vs OPP" / "@OPP" mirrors how the original DK export denoted home/away
// (an "@" prefix on the Opponent column) -- is_home is only null if a row
// couldn't be parsed as either, which shouldn't happen via the CSV loader
// but is defensive against a live scrape hitting an unexpected page shape.
export function opponentLabel(p: { opponent: string; is_home: boolean | null }): string {
  if (p.is_home === null) return p.opponent;
  return p.is_home ? `vs ${p.opponent}` : `@${p.opponent}`;
}

// "RB1" -- position + depth-chart rank, cross-referenced server-side from
// the latest depth-chart snapshot by player name (see backend/services/
// ownership/depth_rank.py). Falls back to just the position when there's
// no depth-chart snapshot yet or this name didn't match one.
export function roleLabel(p: OwnershipPlayer): string {
  return p.rank !== null ? `${p.position}${p.rank}` : p.position;
}

export function playerMatchesFilters(
  p: OwnershipPlayer,
  teamFilter: Set<string>,
  positionFilter: Set<string>
): boolean {
  const teamOk = teamFilter.size === 0 || teamFilter.has(p.team);
  const positionOk = positionFilter.size === 0 || positionFilter.has(p.position);
  return teamOk && positionOk;
}

// Name + role badge, reused by PlayerRow's grid rows and the Pivots
// section's trigger header. Its width comes entirely from whichever parent
// it's in: PlayerRow's rows are a CSS grid with a fixed 200px name column
// (see .ownership-player-row), so this stretches to fill that and
// truncates with "..." if the name doesn't fit; the Pivots trigger header
// is a plain flex row instead, so there it just sizes to the name's own
// content ("dynamic width"). The role badge (e.g. "RB1") sits outside the
// truncated span so it's never the part that gets clipped. Click (or
// Enter/Space) toggles showing the full name, wrapped onto extra lines
// within the same column rather than growing past it. By default this stops
// the click from bubbling, because it sits inside rows that have their own,
// separate click-to-expand behavior (the Pivots section's trigger row) where
// the name-expand and row-expand interactions need to stay independent.
// bubbleClick=true opts out of that for rows where the *entire* row should
// toggle open/closed no matter which part of it you click (Leverage & pivot
// plays) -- the name still expands itself, but the click also reaches the
// row's own handler instead of being swallowed here.
export function PlayerNameCell({
  player,
  role,
  bubbleClick = false,
}: {
  player: string;
  role: string;
  bubbleClick?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);

  function toggle(e: { stopPropagation: () => void }) {
    if (!bubbleClick) {
      e.stopPropagation();
    }
    setExpanded((v) => !v);
  }

  return (
    <span
      className={`ownership-player-name-wrap${expanded ? " expanded" : ""}`}
      role="button"
      tabIndex={0}
      title={player}
      onClick={toggle}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          toggle(e);
        }
      }}
    >
      <span className="ownership-player-name">{player}</span>
      <span className="ownership-role">{role}</span>
    </span>
  );
}

// Shared row for every player list across these views (Chalk, Game
// Leverage's chalk/pivot-candidate subgroups, each pivot group's own
// pivot list, and Salary Blocks' per-block player rows). A CSS grid with
// fixed-width name/salary/pct tracks (see .ownership-player-row) --
// unlike flexbox's proportional shrinking, fixed grid tracks can't drift
// row-to-row depending on how much a given row's content happens to
// overflow, so salary/ownership% always start at the exact same
// x-position no matter what's in the name column.
export function PlayerRow({ p }: { p: OwnershipPlayer }) {
  return (
    <li className="ownership-player-row">
      <PlayerNameCell player={p.player} role={roleLabel(p)} />
      <span className="ownership-player-salary">{formatSalary(p.salary)}</span>
      <span className="ownership-player-pct">{formatOwnershipPct(p.ownership_pct)}</span>
    </li>
  );
}
