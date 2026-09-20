import { useEffect, useMemo, useState } from "react";
import { fetchDepthChartRoster, fetchUsageBumpPlayers, saveUsageBumpPlayers } from "../api";
import type { DepthChartRosterPlayer, UsageBumpTeamEntry } from "../types";
import { CollapsibleHint } from "./CollapsibleHint";
import { PlayerNameAutocomplete } from "./PlayerNameAutocomplete";

// Hand-curated "if this player is out, these named teammates get bumped
// usage" lists (backend/schemas/usage_bump/usage_bump_players.py), edited
// here and read by the (separate, read-only) Usage Bump tab's own live
// scoring -- see backend/services/usage_bump/engine.py. Its own list
// order matters (first name is the biggest beneficiary), and the engine
// only ever uses at most 5 usable names per trigger, so beneficiaries are
// reorderable and capped at 5 here to match.
//
// Player names are free text (matching the file's own format) but
// suggested via PlayerNameAutocomplete against the latest depth-chart
// snapshot (fetchDepthChartRoster) scoped to that row's own team -- a
// beneficiary has to be on the SAME team as the trigger to ever actually
// resolve (see engine.py's own "drop names not on this team's current
// depth chart" step), so suggestions are scoped there too rather than
// across the whole league.
//
// Its own top-level tab rather than a Settings panel -- this list can
// grow to cover a lot of players, and a full-width tab with its own
// search leaves room for that; a cramped Settings panel wouldn't.
// Whole-list Save (like Name Aliases), not per-action saves -- add/edit/
// reorder/remove freely, then Save writes the complete file at once.
//
// Team navigation is a single-select chip row across all 32 teams (the
// depth-chart roster's own team universe), rather than a "+Add Team"
// dropdown plus an always-all-teams list -- with potentially dozens of
// curated trigger players once this list fills out, showing every team's
// section at once made the page unwieldy to scroll, and there was no way
// to jump straight to one team. A team with no curated entry yet is still
// selectable and shows an empty, ready-to-edit state (see
// selectedTeamEntry below) -- the entry itself is only created in `teams`
// once the person actually adds a trigger player, same "don't persist an
// empty row" convention handleSave's own cleanup already relies on.
const MAX_BENEFICIARIES = 5;

interface UsageBumpPlayersViewProps {
  // Reported up to App.tsx (see its own requestViewChange) so switching
  // top-level tabs while there's an unsaved edit here can ask for
  // confirmation first, instead of silently discarding it.
  onDirtyChange?: (dirty: boolean) => void;
}

// Same shape as handleSave's own pre-save cleanup (trim names, drop
// blank trigger rows and blank beneficiary slots) -- used for BOTH the
// actual save payload and the dirty-check comparison below, so an
// add-then-remove of a blank row (or trailing whitespace alone) never
// reads as an unsaved change that isn't really there.
function cleanTeams(teams: UsageBumpTeamEntry[]): UsageBumpTeamEntry[] {
  return teams
    .map((t) => ({
      teamAbbrev: t.teamAbbrev,
      players: t.players
        .filter((p) => p.name.trim())
        .map((p) => ({
          name: p.name.trim(),
          moreUsagePlayers: p.moreUsagePlayers.map((b) => b.trim()).filter(Boolean),
        })),
    }))
    .filter((t) => t.players.length > 0)
    .sort((a, b) => a.teamAbbrev.localeCompare(b.teamAbbrev));
}

export function UsageBumpPlayersView({ onDirtyChange }: UsageBumpPlayersViewProps) {
  const [roster, setRoster] = useState<DepthChartRosterPlayer[]>([]);
  const [teams, setTeams] = useState<UsageBumpTeamEntry[]>([]);
  // The last-persisted shape, compared against `teams` (both cleaned) to
  // decide whether there's an unsaved edit -- set from the initial fetch
  // and again after every successful save.
  const [savedTeams, setSavedTeams] = useState<UsageBumpTeamEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [selectedTeam, setSelectedTeam] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([fetchDepthChartRoster(), fetchUsageBumpPlayers()])
      .then(([rosterResult, usageBumpResult]) => {
        setRoster(rosterResult.players);
        setTeams(usageBumpResult.teams);
        setSavedTeams(usageBumpResult.teams);
      })
      .catch((err) => {
        setRoster([]);
        setTeams([]);
        setSavedTeams([]);
        setLoadError(err instanceof Error ? err.message : "Failed to load usage bump players");
      })
      .finally(() => setLoading(false));
  }, []);

  const isDirty = useMemo(
    () => JSON.stringify(cleanTeams(teams)) !== JSON.stringify(cleanTeams(savedTeams)),
    [teams, savedTeams]
  );

  useEffect(() => {
    onDirtyChange?.(isDirty);
  }, [isDirty, onDirtyChange]);

  const rosterByTeam = useMemo(() => {
    const map = new Map<string, DepthChartRosterPlayer[]>();
    for (const p of roster) {
      if (!map.has(p.team)) map.set(p.team, []);
      map.get(p.team)!.push(p);
    }
    for (const list of map.values()) {
      list.sort((a, b) => a.position.localeCompare(b.position) || a.depth_rank - b.depth_rank);
    }
    return map;
  }, [roster]);

  // All 32 teams from the depth-chart roster itself (not just the ones
  // that happen to already have a curated entry) -- see this module's own
  // comment above for why every team is always selectable.
  const allTeamAbbrevs = useMemo(() => [...new Set(roster.map((p) => p.team))].sort(), [roster]);

  const curatedTeamAbbrevs = useMemo(
    () => new Set(teams.filter((t) => t.players.length > 0).map((t) => t.teamAbbrev)),
    [teams]
  );

  function updateTeam(teamAbbrev: string, updater: (team: UsageBumpTeamEntry) => UsageBumpTeamEntry) {
    setTeams((prev) => {
      if (!prev.some((t) => t.teamAbbrev === teamAbbrev)) {
        return [...prev, updater({ teamAbbrev, players: [] })];
      }
      return prev.map((t) => (t.teamAbbrev === teamAbbrev ? updater(t) : t));
    });
  }

  function addPlayer(teamAbbrev: string) {
    updateTeam(teamAbbrev, (t) => ({ ...t, players: [...t.players, { name: "", moreUsagePlayers: [] }] }));
  }

  function removePlayer(teamAbbrev: string, playerIndex: number) {
    updateTeam(teamAbbrev, (t) => ({ ...t, players: t.players.filter((_, i) => i !== playerIndex) }));
  }

  function updatePlayerName(teamAbbrev: string, playerIndex: number, name: string) {
    updateTeam(teamAbbrev, (t) => ({
      ...t,
      players: t.players.map((p, i) => (i === playerIndex ? { ...p, name } : p)),
    }));
  }

  function addBeneficiary(teamAbbrev: string, playerIndex: number) {
    updateTeam(teamAbbrev, (t) => ({
      ...t,
      players: t.players.map((p, i) => (i === playerIndex ? { ...p, moreUsagePlayers: [...p.moreUsagePlayers, ""] } : p)),
    }));
  }

  function updateBeneficiary(teamAbbrev: string, playerIndex: number, beneficiaryIndex: number, value: string) {
    updateTeam(teamAbbrev, (t) => ({
      ...t,
      players: t.players.map((p, i) =>
        i === playerIndex
          ? { ...p, moreUsagePlayers: p.moreUsagePlayers.map((b, j) => (j === beneficiaryIndex ? value : b)) }
          : p
      ),
    }));
  }

  function removeBeneficiary(teamAbbrev: string, playerIndex: number, beneficiaryIndex: number) {
    updateTeam(teamAbbrev, (t) => ({
      ...t,
      players: t.players.map((p, i) =>
        i === playerIndex ? { ...p, moreUsagePlayers: p.moreUsagePlayers.filter((_, j) => j !== beneficiaryIndex) } : p
      ),
    }));
  }

  function moveBeneficiary(teamAbbrev: string, playerIndex: number, beneficiaryIndex: number, direction: -1 | 1) {
    updateTeam(teamAbbrev, (t) => ({
      ...t,
      players: t.players.map((p, i) => {
        if (i !== playerIndex) return p;
        const target = beneficiaryIndex + direction;
        if (target < 0 || target >= p.moreUsagePlayers.length) return p;
        const next = [...p.moreUsagePlayers];
        [next[beneficiaryIndex], next[target]] = [next[target], next[beneficiaryIndex]];
        return { ...p, moreUsagePlayers: next };
      }),
    }));
  }

  async function handleSave() {
    setSaving(true);
    setMessage(null);
    try {
      // Drop half-filled rows before saving -- a trigger player with no
      // name, or a blank beneficiary slot -- same "don't save broken
      // rows" convention as Name Aliases' own save.
      const cleaned = cleanTeams(teams);
      const result = await saveUsageBumpPlayers({ teams: cleaned });
      setTeams(result.teams);
      setSavedTeams(result.teams);
      setMessage("Saved");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Failed to save usage bump players");
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <p className="hint">Loading…</p>;

  // Rendered both above and below the (potentially long) beneficiary
  // list for the selected team -- same Save button either way, so it's
  // reachable without scrolling all the way down for a team with a lot
  // of curated trigger players.
  const saveControls = (
    <div className="name-aliases-actions">
      <button type="button" className="player-pool-save-button" disabled={saving} onClick={handleSave}>
        {saving ? "Saving…" : "Save"}
      </button>
      {message && <span className="hint">{message}</span>}
      {!message && isDirty && <span className="hint">Unsaved changes</span>}
    </div>
  );

  const selectedTeamEntry: UsageBumpTeamEntry = selectedTeam
    ? teams.find((t) => t.teamAbbrev === selectedTeam) ?? { teamAbbrev: selectedTeam, players: [] }
    : { teamAbbrev: "", players: [] };

  return (
    <>
      <CollapsibleHint
        items={[
          `Hand-curated "if this player is out, these named teammates get bumped usage" lists, in priority order
          (first name is the biggest beneficiary, capped at 5 usable names).`,
          "Read by the Usage Bump tab's own live scoring whenever a listed trigger player has a non-null status.",
          "Most players don't need an entry here at all -- they just fall back to the position-based default list instead.",
          "Name fields suggest real players from the latest depth-chart snapshot, scoped to that row's own team, but still accept free text.",
          "Select a team below to view or edit its list.",
        ]}
      />

      {loadError && <p className="error">{loadError}</p>}

      <div className="filters">
        <div className="chip-filter">
          <span className="filter-label">Team</span>
          <div className="chip-row">
            {allTeamAbbrevs.map((t) => (
              <button
                key={t}
                type="button"
                className={`chip${selectedTeam === t ? " selected" : ""}${
                  curatedTeamAbbrevs.has(t) ? " chip-has-content" : ""
                }`}
                aria-pressed={selectedTeam === t}
                onClick={() => setSelectedTeam(t)}
              >
                {t}
              </button>
            ))}
          </div>
        </div>
      </div>

      {selectedTeam === null && <p className="hint">Select a team above to view or edit its usage bump players.</p>}

      {selectedTeam !== null && (
        <>
          {saveControls}

          <section className="ownership-section usage-bump-players-team">
            <div className="player-pool-grid-header">
              <h2>{selectedTeamEntry.teamAbbrev}</h2>
            </div>

            {selectedTeamEntry.players.length === 0 && (
              <p className="hint">No curated trigger players for this team yet.</p>
            )}

            {selectedTeamEntry.players.map((player, playerIndex) => (
              <div className="usage-bump-player-row" key={playerIndex}>
                <div className="usage-bump-trigger-row">
                  <PlayerNameAutocomplete
                    value={player.name}
                    onChange={(name) => updatePlayerName(selectedTeamEntry.teamAbbrev, playerIndex, name)}
                    candidates={rosterByTeam.get(selectedTeamEntry.teamAbbrev) ?? []}
                    placeholder="Trigger player"
                    className="usage-bump-trigger-input"
                  />
                  <button
                    type="button"
                    onClick={() => removePlayer(selectedTeamEntry.teamAbbrev, playerIndex)}
                    aria-label={`Remove ${player.name || "player"}`}
                  >
                    ✕
                  </button>
                </div>

                <ol className="usage-bump-beneficiary-list">
                  {player.moreUsagePlayers.map((beneficiary, beneficiaryIndex) => (
                    <li key={beneficiaryIndex} className="usage-bump-beneficiary-row">
                      <span className="usage-bump-beneficiary-rank">{beneficiaryIndex + 1}</span>
                      <PlayerNameAutocomplete
                        value={beneficiary}
                        onChange={(value) =>
                          updateBeneficiary(selectedTeamEntry.teamAbbrev, playerIndex, beneficiaryIndex, value)
                        }
                        candidates={rosterByTeam.get(selectedTeamEntry.teamAbbrev) ?? []}
                        excludeNames={[player.name, ...player.moreUsagePlayers.filter((_, j) => j !== beneficiaryIndex)]}
                        placeholder="Beneficiary player"
                      />
                      <button
                        type="button"
                        disabled={beneficiaryIndex === 0}
                        onClick={() => moveBeneficiary(selectedTeamEntry.teamAbbrev, playerIndex, beneficiaryIndex, -1)}
                        aria-label="Move up"
                      >
                        ↑
                      </button>
                      <button
                        type="button"
                        disabled={beneficiaryIndex === player.moreUsagePlayers.length - 1}
                        onClick={() => moveBeneficiary(selectedTeamEntry.teamAbbrev, playerIndex, beneficiaryIndex, 1)}
                        aria-label="Move down"
                      >
                        ↓
                      </button>
                      <button
                        type="button"
                        onClick={() => removeBeneficiary(selectedTeamEntry.teamAbbrev, playerIndex, beneficiaryIndex)}
                        aria-label="Remove beneficiary"
                      >
                        ✕
                      </button>
                    </li>
                  ))}
                </ol>
                {player.moreUsagePlayers.length < MAX_BENEFICIARIES && (
                  <button
                    type="button"
                    className="usage-bump-add-beneficiary"
                    onClick={() => addBeneficiary(selectedTeamEntry.teamAbbrev, playerIndex)}
                  >
                    + Add beneficiary
                  </button>
                )}
              </div>
            ))}

            <button type="button" onClick={() => addPlayer(selectedTeamEntry.teamAbbrev)}>
              + Add trigger player
            </button>
          </section>

          {saveControls}
        </>
      )}
    </>
  );
}
