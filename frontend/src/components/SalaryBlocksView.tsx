import { useEffect, useState } from "react";
import { fetchPositionBlocks } from "../api";
import type { PositionBlock, PositionBlocksResult } from "../types";
import { ChipMultiSelect } from "./ChipMultiSelect";
import { PlayerSearchSelect } from "./PlayerSearchSelect";
import { PlayerRow, formatSalary, roleLabel } from "./playerDisplay";

// Mirrors backend/services/ownership/position_blocks.py's
// ALLOWED_BLOCK_SIZES -- QB/DST aren't offered at all (single-per-team
// roster slots, same reasoning as Game Leverage's exclusion), and sizes
// reflect DK roster requirements: 1 mandatory TE (blocks of 2), 2
// mandatory RBs (2 or 3, the 3rd covering FLEX), 3 mandatory WRs (2, 3,
// or 4, the 4th covering FLEX).
const POSITIONS = ["RB", "WR", "TE"] as const;
type Position = (typeof POSITIONS)[number];

const BLOCK_SIZE_OPTIONS: Record<Position, number[]> = {
  RB: [2, 3],
  WR: [2, 3, 4],
  TE: [2],
};

// Mirrors backend/services/ownership/position_blocks.py's SALARY_CAPS --
// used to resolve "% of cap" into dollars for the salary filter below.
// The platform itself now comes from the shared Settings panel (see
// App.tsx) rather than a filter here; DEFAULT_CAP covers any platform
// without its own entry yet (only DraftKings has a real file format
// behind it today -- see backend/services/platform_settings/prefix.py).
const DEFAULT_CAP = 50000;
const PLATFORM_CAPS: Record<string, number> = {
  DraftKings: DEFAULT_CAP,
};

// Mirrors backend's SALARY_BUCKETS -- percent-of-cap ranges, [min, max).
// null max means "and up". Dollar labels are computed from the selected
// platform's cap (see salaryBucketLabel) rather than hardcoded, since the
// same bucket could mean a different dollar amount on a different
// platform.
const SALARY_BUCKETS: { id: string; minPct: number; maxPct: number | null }[] = [
  { id: "under_20", minPct: 0, maxPct: 20 },
  { id: "20_30", minPct: 20, maxPct: 30 },
  { id: "30_40", minPct: 30, maxPct: 40 },
  { id: "40_50", minPct: 40, maxPct: 50 },
  { id: "50_60", minPct: 50, maxPct: 60 },
  { id: "60_plus", minPct: 60, maxPct: null },
];

// The underlying range is still half-open [minPct, maxPct) -- only the
// display changes here. For every bucket except the first and last, the
// upper edge displays one point/one dollar short of the next bucket's
// start (e.g. "20-29% ($10,000-$14,900)" for the 20-30% bucket) so
// adjacent buckets read as covering non-overlapping ranges rather than
// both appearing to include $15,000.
function salaryBucketLabel(bucket: (typeof SALARY_BUCKETS)[number], cap: number): string {
  const minDollar = formatSalary(Math.round((cap * bucket.minPct) / 100));
  if (bucket.maxPct === null) {
    return `${bucket.minPct}%+ (${minDollar}+)`;
  }
  const maxDollarExclusive = Math.round((cap * bucket.maxPct) / 100);
  if (bucket.minPct === 0) {
    return `< ${bucket.maxPct}% (< ${formatSalary(maxDollarExclusive)})`;
  }
  const displayMaxPct = bucket.maxPct - 1;
  const displayMaxDollar = formatSalary(maxDollarExclusive - 100);
  return `${bucket.minPct}-${displayMaxPct}% (${minDollar}-${displayMaxDollar})`;
}

function blockKey(block: PositionBlock): string {
  return block.players.map((p) => p.player).join("|");
}

type SortDirection = "desc" | "asc";

// Every distinct player name appearing across the currently-fetched
// blocks (i.e. after the server-side team/game/salary-bucket/scope
// filters, but before the player-name filter below is applied to them) --
// this is what populates the "Filter by player" chips, so the option list
// naturally narrows as those other filters narrow the underlying pool,
// the same way the team/game filter options are derived from the loaded
// data rather than hardcoded.
function playersInBlocks(blocks: PositionBlock[]): string[] {
  return [...new Set(blocks.flatMap((b) => b.players.map((p) => p.player)))].sort();
}

// season/week/platform come from the shared header control / Settings
// panel (see App.tsx) rather than being owned here.
interface SalaryBlocksViewProps {
  season: number;
  week: number;
  platform: string;
}

export function SalaryBlocksView({ season, week, platform }: SalaryBlocksViewProps) {
  const [position, setPosition] = useState<Position>("RB");
  const [blockSize, setBlockSize] = useState(2);
  const [sameGameOnly, setSameGameOnly] = useState(false);
  const [teamFilter, setTeamFilter] = useState<Set<string>>(new Set());
  const [gameFilterLabels, setGameFilterLabels] = useState<Set<string>>(new Set());
  const [salaryBucketLabels, setSalaryBucketLabels] = useState<Set<string>>(new Set());

  const [data, setData] = useState<PositionBlocksResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");
  const [playerFilter, setPlayerFilter] = useState<Set<string>>(new Set());
  const [expandedBlocks, setExpandedBlocks] = useState<Set<string>>(new Set());

  function toggleBlock(key: string) {
    setExpandedBlocks((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  }

  function selectPosition(next: Position) {
    setPosition(next);
    // A block size valid for the old position (e.g. WR's 4) may not be
    // valid for the new one (TE only ever offers 2) -- fall back to that
    // position's first/smallest option rather than sending an invalid
    // combination the backend would just reject.
    if (!BLOCK_SIZE_OPTIONS[next].includes(blockSize)) {
      setBlockSize(BLOCK_SIZE_OPTIONS[next][0]);
    }
  }

  useEffect(() => {
    // Bucket labels bake in the dollar amount for the *current* platform's
    // cap (e.g. "20-30% ($10,000-$15,000)") -- if the shared platform
    // setting changes, that dollar amount changes too, so a label picked
    // under the old platform wouldn't match anything under the new one.
    // Clearing avoids a selection that looks checked but silently stops
    // filtering anything.
    setSalaryBucketLabels(new Set());
  }, [platform]);

  const labelToKey = new Map((data?.games ?? []).map((g) => [g.label, g.key]));
  // Every team with at least one player at this position, derived from
  // the (position-scoped, pre-filter) games list rather than a separate
  // API field -- each game key is "TEAM1-TEAM2", so splitting and
  // deduping across every game gives exactly that set.
  const teamOptions = [...new Set((data?.games ?? []).flatMap((g) => g.key.split("-")))].sort();
  const gameOptions = (data?.games ?? []).map((g) => g.label);

  const cap = PLATFORM_CAPS[platform] ?? DEFAULT_CAP;
  const salaryBucketOptions = SALARY_BUCKETS.map((b) => salaryBucketLabel(b, cap));
  const salaryBucketLabelToId = new Map(SALARY_BUCKETS.map((b) => [salaryBucketLabel(b, cap), b.id]));

  // Sorting and the player-name filter both apply client-side to the
  // already-fetched blocks -- unlike team/game/salary-bucket (which narrow
  // the combinatorics the backend has to generate in the first place),
  // these only reorder/narrow a result set already small enough to have
  // been returned, so there's no need for a round-trip.
  const playerOptions = playersInBlocks(data?.blocks ?? []);
  const displayedBlocks = [...(data?.blocks ?? [])]
    .filter((block) => playerFilter.size === 0 || block.players.some((p) => playerFilter.has(p.player)))
    .sort((a, b) => (sortDirection === "desc" ? b.total_salary - a.total_salary : a.total_salary - b.total_salary));

  useEffect(() => {
    setLoading(true);
    setError(null);

    fetchPositionBlocks({
      season,
      week,
      position,
      blockSize,
      sameGameOnly,
      teams: [...teamFilter],
      games: [...gameFilterLabels].map((label) => labelToKey.get(label)).filter((key): key is string => !!key),
      platform,
      salaryBuckets: [...salaryBucketLabels]
        .map((label) => salaryBucketLabelToId.get(label))
        .filter((id): id is string => !!id),
    })
      .then((result) => setData(result))
      .catch((err) => {
        setData(null);
        setError(err instanceof Error ? err.message : "Failed to load position blocks");
      })
      .finally(() => setLoading(false));
    // labelToKey/salaryBucketLabelToId are both derived from state this
    // effect itself sets or from a platform-derived constant already
    // listed below -- including them would re-run the effect off of its
    // own result. Every other input that should trigger a refetch is
    // listed explicitly.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [season, week, position, blockSize, sameGameOnly, teamFilter, gameFilterLabels, platform, salaryBucketLabels]);

  const isNotFound = error !== null && error.includes("No DK salary file uploaded yet");

  return (
    <>
      <div className="filters">
        <div className="chip-filter">
          <span className="filter-label">Position</span>
          <div className="chip-row">
            {POSITIONS.map((p) => (
              <button
                key={p}
                type="button"
                className={`chip${position === p ? " selected" : ""}`}
                aria-pressed={position === p}
                onClick={() => selectPosition(p)}
              >
                {p}
              </button>
            ))}
          </div>
        </div>

        <div className="chip-filter">
          <span className="filter-label">Block size</span>
          <div className="chip-row">
            {BLOCK_SIZE_OPTIONS[position].map((size) => (
              <button
                key={size}
                type="button"
                className={`chip${blockSize === size ? " selected" : ""}`}
                aria-pressed={blockSize === size}
                onClick={() => setBlockSize(size)}
              >
                {size}
              </button>
            ))}
          </div>
        </div>

        <div className="chip-filter">
          <span className="filter-label">Scope</span>
          <div className="chip-row">
            <button
              type="button"
              className={`chip${sameGameOnly ? " selected" : ""}`}
              aria-pressed={sameGameOnly}
              onClick={() => setSameGameOnly(true)}
            >
              Same game
            </button>
            <button
              type="button"
              className={`chip${!sameGameOnly ? " selected" : ""}`}
              aria-pressed={!sameGameOnly}
              onClick={() => setSameGameOnly(false)}
            >
              Any game
            </button>
          </div>
        </div>

        <ChipMultiSelect label="Filter by team" options={teamOptions} selected={teamFilter} onChange={setTeamFilter} />
        <ChipMultiSelect label="Filter by game" options={gameOptions} selected={gameFilterLabels} onChange={setGameFilterLabels} />
        <ChipMultiSelect
          label="Filter by salary"
          options={salaryBucketOptions}
          selected={salaryBucketLabels}
          onChange={setSalaryBucketLabels}
        />
        <PlayerSearchSelect label="Filter by player" options={playerOptions} selected={playerFilter} onChange={setPlayerFilter} />

        <div className="chip-filter">
          <span className="filter-label">Sort by salary</span>
          <div className="chip-row">
            <button
              type="button"
              className={`chip${sortDirection === "desc" ? " selected" : ""}`}
              aria-pressed={sortDirection === "desc"}
              onClick={() => setSortDirection("desc")}
            >
              High to low
            </button>
            <button
              type="button"
              className={`chip${sortDirection === "asc" ? " selected" : ""}`}
              aria-pressed={sortDirection === "asc"}
              onClick={() => setSortDirection("asc")}
            >
              Low to high
            </button>
          </div>
        </div>
      </div>

      {loading && <p className="hint">Loading…</p>}
      {!loading && error && isNotFound && (
        <p className="hint">
          No DK salary file uploaded yet for season {season} week {week} -- upload it in the Settings tab.
        </p>
      )}
      {!loading && error && !isNotFound && <p className="error">{error}</p>}

      {!loading && !error && data && (
        <section className="ownership-section">
          <h2>
            {blockSize} {position} blocks
          </h2>
          {displayedBlocks.length === 0 ? (
            <p className="hint">No blocks match the current filters.</p>
          ) : (
            <ul className="ownership-player-list pivot-card-list">
              {displayedBlocks.map((block) => {
                const key = blockKey(block);
                const open = expandedBlocks.has(key);
                const names = block.players
                  .map((p) => `${p.player} ${roleLabel(p)} ${formatSalary(p.salary)}`)
                  .join(" / ");
                return (
                  <li key={key} className="ownership-pivot-group">
                    <div
                      className="block-summary"
                      role="button"
                      tabIndex={0}
                      aria-expanded={open}
                      onClick={() => toggleBlock(key)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          toggleBlock(key);
                        }
                      }}
                    >
                      <span className="block-total">{formatSalary(block.total_salary)}</span>
                      <span className="block-names">{names}</span>
                      <span className="block-arrow">{open ? "▴" : "▾"}</span>
                    </div>
                    {open && (
                      <ul className="ownership-player-list ownership-pivot-list">
                        {block.players.map((p) => (
                          <PlayerRow key={p.player} p={p} />
                        ))}
                      </ul>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      )}
    </>
  );
}
