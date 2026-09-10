import { useEffect, useState } from "react";
import { fetchGameBlocks, fetchPositionBlocks } from "../api";
import type { GameBlock, GameBlocksResult, GameOption, OwnershipPlayer, PositionBlocksResult } from "../types";
import { ChipMultiSelect } from "./ChipMultiSelect";
import { PlayerSearchSelect } from "./PlayerSearchSelect";
import { PlayerRow, formatExpectedFpts, formatSalary, roleLabel } from "./playerDisplay";

// Single position (the original feature) generates same-position
// combinations one position at a time (see ALLOWED_BLOCK_SIZES below).
// Onslaught is a "game block" instead -- RB/WR/TE mixed freely, both teams
// in one game (see backend/services/ownership/game_blocks.py), narrowed
// by its own "team"/"bring back team" size filters below.
const BLOCK_TYPES = [
  { id: "single", label: "Single position" },
  { id: "onslaught", label: "Onslaught" },
] as const;
type BlockType = (typeof BLOCK_TYPES)[number]["id"];

// Onslaught's own "bring back team" (minority-side) filter --
// GameBlock.bringback_count, offered as chips the same way salary buckets
// are rather than a free-text input.
const BRINGBACK_SIZES = [1, 2, 3, 4] as const;

// Onslaught's own "team" (majority-side) filter -- GameBlock.primary_count.
const PRIMARY_SIZES = [1, 2, 3, 4, 5] as const;

// Onslaught's own overall block-size cap -- bigger than the backend's
// default (see game_blocks.py's MAX_GAME_BLOCK_SIZE) so PRIMARY_SIZES/
// BRINGBACK_SIZES above have larger blocks to actually match against.
// Single position uses the backend's own default instead (fetchPositionBlocks
// has no maxSize param at all).
const ONSLAUGHT_MAX_SIZE = 7;

// Common shape both PositionBlock and GameBlock satisfy -- blockKey/
// playersInBlocks/sorting/filtering below only ever touch these three
// fields, so they work unchanged regardless of which block type is
// currently selected.
interface BlockLike {
  players: OwnershipPlayer[];
  total_salary: number;
  total_expected_fpts: number;
}

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

// "Same team players" filter (Single position tab only) -- how many
// players within a block share one team, exact match, multi-select same
// convention as the salary-bucket chips. Deliberately capped one below
// each position's own max block size (RB/TE's own max of 3/2 -> 2, WR's
// own max of 4 -> 3) rather than offering every value up to the block's
// full size -- a block where literally every player is on the same team
// is vanishingly rare for any position with more than a couple of
// relevant players per team, so that top value isn't worth its own chip.
const SAME_TEAM_SIZE_OPTIONS: Record<Position, number[]> = {
  RB: [1, 2],
  WR: [1, 2, 3],
  TE: [1, 2],
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

function blockKey(block: BlockLike): string {
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
function playersInBlocks(blocks: BlockLike[]): string[] {
  return [...new Set(blocks.flatMap((b) => b.players.map((p) => p.player)))].sort();
}

// season/week/platform come from the shared header control / Settings
// panel (see App.tsx) rather than being owned here.
interface SalaryBlocksViewProps {
  season: number;
  week: number;
  platform: string;
  contest: string;
}

export function SalaryBlocksView({ season, week, platform, contest }: SalaryBlocksViewProps) {
  const [blockType, setBlockType] = useState<BlockType>("single");
  const [position, setPosition] = useState<Position>("RB");
  const [blockSize, setBlockSize] = useState(2);
  const [sameGameOnly, setSameGameOnly] = useState(false);
  // Single position tab's own "Same team players" filter -- see
  // SAME_TEAM_SIZE_OPTIONS. Closed set, no "All" chip (see its
  // ChipMultiSelect below) -- defaults to "1" (all-different-teams, the
  // more common case) rather than starting empty/unfiltered.
  const [sameTeamSizes, setSameTeamSizes] = useState<Set<string>>(new Set(["1"]));
  const [bringbackSizes, setBringbackSizes] = useState<Set<string>>(new Set());
  // Onslaught-only "team" (majority-side) filter -- see PRIMARY_SIZES.
  const [primarySizes, setPrimarySizes] = useState<Set<string>>(new Set());
  const [teamFilter, setTeamFilter] = useState<Set<string>>(new Set());
  const [gameFilterLabels, setGameFilterLabels] = useState<Set<string>>(new Set());
  const [salaryBucketLabels, setSalaryBucketLabels] = useState<Set<string>>(new Set());

  // Only one of these is ever populated at a time, matching whichever
  // endpoint blockType currently calls for -- kept separate rather than a
  // single union-typed `data` so the rest of the component doesn't need to
  // runtime-check which shape it got back.
  const [positionData, setPositionData] = useState<PositionBlocksResult | null>(null);
  const [gameData, setGameData] = useState<GameBlocksResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");
  const [playerFilter, setPlayerFilter] = useState<Set<string>>(new Set());
  const [expandedBlocks, setExpandedBlocks] = useState<Set<string>>(new Set());

  // "Filter by team"/"Filter by game" options -- kept separate from
  // positionData/gameData (and NOT cleared when a fetch fails, e.g. a
  // combinatorial-safety-cap error on a wide-open Single position query)
  // so those two filters stay usable even when the current filter
  // combination itself returns no blocks or errors out. Only reset when
  // the underlying dataset actually changes (season/week/platform), so a
  // stale team/game list from a different week never lingers -- see the
  // effect below.
  const [gamesList, setGamesList] = useState<GameOption[]>([]);

  const isGameBlockType = blockType !== "single";
  // Onslaught has no team filter (a full game-block always wants both
  // teams anyway, so "filter by team" doesn't narrow it the way it would
  // Single position) -- game selection is the primary way to scope it
  // instead, so results wait until at least one game is picked.
  const onslaughtNeedsGameSelection = blockType === "onslaught" && gameFilterLabels.size === 0;

  // Onslaught only ever allows one game selected at a time -- a full game
  // block already spans both teams in that one game, so "more than one
  // game at once" would just silently union two unrelated games' blocks
  // together. ChipMultiSelect's onChange always hands back the *full*
  // next set (its own toggle() adds/removes just the clicked chip from
  // the current selection) -- picking a second chip while one's already
  // selected should replace it, not add to it, so this only ever keeps
  // whichever chip wasn't already selected.
  function handleOnslaughtGameFilterChange(next: Set<string>) {
    if (next.size <= 1) {
      setGameFilterLabels(next);
      return;
    }
    const added = [...next].find((label) => !gameFilterLabels.has(label));
    setGameFilterLabels(new Set(added ? [added] : []));
  }

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
    // Same idea for "Same team players" -- e.g. a selected "3" carried
    // over from WR isn't a valid chip for RB/TE (see
    // SAME_TEAM_SIZE_OPTIONS), so drop whatever no longer applies. Unlike
    // block size, more than one value can be selected here -- only fall
    // back to the first option if every selected value turned out
    // invalid, since (having no "All" chip) this filter should never end
    // up with nothing selected at all.
    setSameTeamSizes((prev) => {
      const stillValid = new Set([...prev].filter((size) => SAME_TEAM_SIZE_OPTIONS[next].includes(Number(size))));
      return stillValid.size > 0 ? stillValid : new Set([String(SAME_TEAM_SIZE_OPTIONS[next][0])]);
    });
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

  useEffect(() => {
    // A new season/week/platform/contest means an entirely different
    // salary file -- last week's teams/games would be actively wrong
    // here, not just stale, so (unlike an ordinary fetch error) this does
    // clear the list.
    setGamesList([]);
  }, [season, week, platform, contest]);

  const blocks: BlockLike[] = isGameBlockType ? gameData?.blocks ?? [] : positionData?.blocks ?? [];

  const labelToKey = new Map(gamesList.map((g) => [g.label, g.key]));
  // Every team with at least one eligible player, derived from the
  // (pre-filter) games list rather than a separate API field -- each game
  // key is "TEAM1-TEAM2", so splitting and deduping across every game
  // gives exactly that set.
  const teamOptions = [...new Set(gamesList.flatMap((g) => g.key.split("-")))].sort();
  const gameOptions = gamesList.map((g) => g.label);

  const cap = PLATFORM_CAPS[platform] ?? DEFAULT_CAP;
  const salaryBucketOptions = SALARY_BUCKETS.map((b) => salaryBucketLabel(b, cap));
  const salaryBucketLabelToId = new Map(SALARY_BUCKETS.map((b) => [salaryBucketLabel(b, cap), b.id]));

  // Sorting and the player-name filter both apply client-side to the
  // already-fetched blocks -- unlike team/game/salary-bucket (which narrow
  // the combinatorics the backend has to generate in the first place),
  // these only reorder/narrow a result set already small enough to have
  // been returned, so there's no need for a round-trip.
  const playerOptions = playersInBlocks(blocks);
  const displayedBlocks = [...blocks]
    .filter((block) => playerFilter.size === 0 || block.players.some((p) => playerFilter.has(p.player)))
    .sort((a, b) => (sortDirection === "desc" ? b.total_salary - a.total_salary : a.total_salary - b.total_salary));

  useEffect(() => {
    setLoading(true);
    setError(null);

    // Onslaught has no team filter of its own (see the hidden ChipMultiSelect
    // below) -- any leftover selection from Single position shouldn't
    // silently narrow it, so teams is always [] here regardless of
    // teamFilter's current state.
    const teams = blockType === "onslaught" ? [] : [...teamFilter];
    const selectedGames = [...gameFilterLabels].map((label) => labelToKey.get(label)).filter((key): key is string => !!key);
    const salaryBuckets = [...salaryBucketLabels].map((label) => salaryBucketLabelToId.get(label)).filter((id): id is string => !!id);
    // Onslaught defers actually generating blocks until a game is picked --
    // before that, this only asks the backend for the (cheap) games list so
    // "Filter by game" has something to show (see fetchGameBlocks'
    // gamesOnly and this file's own onslaughtNeedsGameSelection).
    const gamesOnly = blockType === "onslaught" && selectedGames.length === 0;

    const request = isGameBlockType
      ? fetchGameBlocks({
          season,
          week,
          teams,
          games: selectedGames,
          platform,
          contest,
          salaryBuckets,
          primarySizes: blockType === "onslaught" ? [...primarySizes].map(Number) : [],
          bringbackSizes: [...bringbackSizes].map(Number),
          maxSize: blockType === "onslaught" ? ONSLAUGHT_MAX_SIZE : undefined,
          gamesOnly,
        }).then((result) => {
          setGameData(result);
          setPositionData(null);
          setGamesList(result.games);
        })
      : fetchPositionBlocks({
          season,
          week,
          position,
          blockSize,
          sameGameOnly,
          teams,
          games: selectedGames,
          platform,
          contest,
          salaryBuckets,
          sameTeamSizes: [...sameTeamSizes].map(Number),
        }).then((result) => {
          setPositionData(result);
          setGameData(null);
          setGamesList(result.games);
        });

    request
      .catch((err) => {
        // Deliberately leaves gamesList (and therefore the "Filter by
        // team"/"Filter by game" chip options) untouched here -- a request
        // that errors out (e.g. an overly-broad Single position query
        // hitting the combinatorial safety cap) shouldn't take those
        // filters away, since narrowing by team/game is usually exactly
        // how you'd recover from that error.
        setPositionData(null);
        setGameData(null);
        setError(err instanceof Error ? err.message : "Failed to load blocks");
      })
      .finally(() => setLoading(false));
    // labelToKey/salaryBucketLabelToId are both derived from state this
    // effect itself sets or from a platform-derived constant already
    // listed below -- including them would re-run the effect off of its
    // own result. Every other input that should trigger a refetch is
    // listed explicitly.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    season,
    week,
    blockType,
    position,
    blockSize,
    sameGameOnly,
    sameTeamSizes,
    primarySizes,
    bringbackSizes,
    teamFilter,
    gameFilterLabels,
    platform,
    contest,
    salaryBucketLabels,
  ]);

  const isNotFound = error !== null && error.includes("No DK salary file uploaded yet");

  return (
    <>
      <div className="filters">
        <div className="chip-filter">
          <span className="filter-label">Block type</span>
          <div className="chip-row">
            {BLOCK_TYPES.map((t) => (
              <button
                key={t.id}
                type="button"
                className={`chip${blockType === t.id ? " selected" : ""}`}
                aria-pressed={blockType === t.id}
                onClick={() => setBlockType(t.id)}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>

        {!isGameBlockType && (
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
        )}

        {!isGameBlockType && (
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
        )}

        {!isGameBlockType && (
          <ChipMultiSelect
            label="Same team players"
            options={SAME_TEAM_SIZE_OPTIONS[position].map(String)}
            selected={sameTeamSizes}
            onChange={setSameTeamSizes}
            showAllOption={false}
          />
        )}

        {isGameBlockType && <p className="hint">2-7 RB/WR/TE players from one game, drawn from both teams.</p>}

        {blockType === "onslaught" && (
          <ChipMultiSelect label="Team size" options={PRIMARY_SIZES.map(String)} selected={primarySizes} onChange={setPrimarySizes} />
        )}

        {isGameBlockType && (
          <ChipMultiSelect
            label="Bring back team size"
            options={BRINGBACK_SIZES.map(String)}
            selected={bringbackSizes}
            onChange={setBringbackSizes}
          />
        )}

        {!isGameBlockType && (
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
        )}

        {blockType !== "onslaught" && (
          <ChipMultiSelect label="Filter by team" options={teamOptions} selected={teamFilter} onChange={setTeamFilter} />
        )}
        <ChipMultiSelect
          label="Filter by game"
          options={gameOptions}
          selected={gameFilterLabels}
          onChange={blockType === "onslaught" ? handleOnslaughtGameFilterChange : setGameFilterLabels}
          showAllOption={blockType !== "onslaught"}
        />
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

      {!loading && !error && (positionData || gameData) && (
        <section className="ownership-section">
          <h2>
            {blockType === "single" && `${blockSize} ${position} blocks`}
            {blockType === "onslaught" && "Onslaught blocks"}
          </h2>
          {isGameBlockType && gameData && gameData.skipped_games.length > 0 && (
            <p className="hint">Skipped (too many players to enumerate): {gameData.skipped_games.map((g) => g.label).join(", ")}.</p>
          )}
          {onslaughtNeedsGameSelection ? (
            <p className="hint">Select a game above to see its Onslaught blocks.</p>
          ) : displayedBlocks.length === 0 ? (
            <p className="hint">No blocks match the current filters.</p>
          ) : (
            <ul className="ownership-player-list pivot-card-list">
              {displayedBlocks.map((block) => {
                const key = blockKey(block);
                const open = expandedBlocks.has(key);
                // Only set for Onslaught -- see BlockLike's own comment for
                // why displayedBlocks itself stays typed generically across
                // both block shapes.
                const gameBlock = isGameBlockType ? (block as GameBlock) : null;
                const names = block.players
                  .map(
                    (p) =>
                      `${p.player} ${roleLabel(p)} ${p.team} ${formatSalary(p.salary)}` +
                      (p.expected_fpts !== null ? ` (${formatExpectedFpts(p.expected_fpts)} FPTS)` : "")
                  )
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
                      <span className="block-total">
                        {formatSalary(block.total_salary)}
                        {block.total_expected_fpts > 0 && (
                          <span className="block-expected-fpts"> ({formatExpectedFpts(block.total_expected_fpts)} FPTS)</span>
                        )}
                      </span>
                      {gameBlock && (
                        <span className="block-team-split">
                          {gameBlock.primary_team} {gameBlock.primary_count} + {gameBlock.bringback_team}{" "}
                          {gameBlock.bringback_count} bring-back
                        </span>
                      )}
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
