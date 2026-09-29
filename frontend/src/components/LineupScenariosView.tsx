import { useEffect, useState } from "react";
import { evaluateLineupScenarios, fetchScheduleGames, uploadLineupScenarioCsv } from "../api";
import type { GameOption, LineupScenarioAnalysis, LineupScenarioDefinition, LineupScenarioTeamFlag, ScenarioRole } from "../types";
import { CollapsibleHint } from "./CollapsibleHint";

interface LineupScenariosViewProps {
  season: number;
  week: number;
  platform: string;
  contest: string;
}

// Depth-chart-specific slots only (no bare "RB"/"WR") -- a resolved
// UploadedLineupPlayer.depth_slot is always one of these (or null), never
// a coarse position, so a chip for plain "RB" would never match anything.
const ALL_DEPTH_SLOTS = ["QB1", "RB1", "RB2", "WR1", "WR2", "WR3", "TE1", "TE2", "DST"];
const ALL_SKILL_SLOTS = ["QB1", "RB1", "RB2", "WR1", "WR2", "WR3", "TE1", "TE2"];
const RB_SLOTS = ["RB1", "RB2"];
const RECEIVING_SLOTS = ["WR1", "WR2", "WR3", "TE1", "TE2"];

// Every selectable role plus a human label and the depth slots this picker
// pre-fills when the role is chosen -- purely a frontend UX default, the
// caller can still edit the position chips freely afterward. "" is not a
// real ScenarioRole -- it's this picker's own "unset" state for a flag row,
// filtered out of the request payload in buildTeamFlags below.
const ROLE_OPTIONS: { value: ScenarioRole | ""; label: string; defaultPositions: string[] }[] = [
  { value: "", label: "Choose a role…", defaultPositions: [] },
  { value: "high_scoring", label: "High scoring (shootout side)", defaultPositions: ALL_SKILL_SLOTS },
  { value: "low_scoring", label: "Low scoring (under implied total)", defaultPositions: ["DST", ...RB_SLOTS] },
  { value: "positive_script", label: "Positive script (winning/leading)", defaultPositions: RB_SLOTS },
  { value: "negative_script", label: "Negative script (losing/trailing)", defaultPositions: RECEIVING_SLOTS },
  { value: "pass_funnel", label: "Pass funnel (heavy volume)", defaultPositions: RECEIVING_SLOTS },
  { value: "extended_game", label: "Extended game (OT/back-and-forth)", defaultPositions: ALL_SKILL_SLOTS },
  { value: "any", label: "Any (just show up)", defaultPositions: [] },
];

function defaultPositionsForRole(role: ScenarioRole | ""): string[] {
  return ROLE_OPTIONS.find((r) => r.value === role)?.defaultPositions ?? [];
}

// One flag row within one side (away/home) of one game -- role="" means
// this particular row hasn't had a role picked yet (a freshly-added row).
interface RoleSelection {
  role: ScenarioRole | "";
  positions: string[];
}

// Keyed by game, each side holds a LIST of flag rows so the same team can
// carry more than one role at once (e.g. this team's RB1 for positive
// script AND its WR1/WR2 for pass funnel, both counted independently) --
// collapsed into a flat LineupScenarioTeamFlag[] only once "Add scenario"
// is clicked (see buildTeamFlags below).
type GameRoleFlags = Record<string, { away: RoleSelection[]; home: RoleSelection[] }>;

function buildTeamFlags(games: GameOption[], flags: GameRoleFlags): LineupScenarioTeamFlag[] {
  const teamFlags: LineupScenarioTeamFlag[] = [];
  for (const game of games) {
    const [away, home] = game.label.split(" @ ");
    const sides = flags[game.key];
    if (!sides) continue;
    for (const selection of sides.away) {
      if (selection.role && away) teamFlags.push({ team: away, role: selection.role, positions: selection.positions });
    }
    for (const selection of sides.home) {
      if (selection.role && home) teamFlags.push({ team: home, role: selection.role, positions: selection.positions });
    }
  }
  return teamFlags;
}

export function LineupScenariosView({ season, week, platform, contest }: LineupScenariosViewProps) {
  const [games, setGames] = useState<GameOption[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const [builderLabel, setBuilderLabel] = useState("");
  const [builderFlags, setBuilderFlags] = useState<GameRoleFlags>({});
  const [scenarios, setScenarios] = useState<LineupScenarioDefinition[]>([]);
  const [minStackSize, setMinStackSize] = useState(1);

  const [evaluating, setEvaluating] = useState(false);
  const [evaluateError, setEvaluateError] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<LineupScenarioAnalysis | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchScheduleGames(season, week, platform, contest)
      .then((result) => {
        if (!cancelled) setGames(result.games);
      })
      .catch(() => {
        if (!cancelled) setGames([]);
      });
    return () => {
      cancelled = true;
    };
  }, [season, week, platform, contest]);

  async function handleUpload() {
    if (!file) return;
    setUploading(true);
    setUploadMessage(null);
    setUploadError(null);
    try {
      const result = await uploadLineupScenarioCsv(season, week, platform, contest, file);
      setUploadMessage(`Loaded ${result.lineup_count} lineups (${result.roster_positions.join(", ")})`);
      setFile(null);
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Failed to upload lineups CSV");
    } finally {
      setUploading(false);
    }
  }

  function sidesFor(gameKey: string) {
    return builderFlags[gameKey] ?? { away: [], home: [] };
  }

  function addRow(gameKey: string, side: "away" | "home") {
    setBuilderFlags((prev) => {
      const current = sidesFor(gameKey);
      return { ...prev, [gameKey]: { ...current, [side]: [...current[side], { role: "", positions: [] }] } };
    });
  }

  function removeRow(gameKey: string, side: "away" | "home", rowIndex: number) {
    setBuilderFlags((prev) => {
      const current = sidesFor(gameKey);
      return { ...prev, [gameKey]: { ...current, [side]: current[side].filter((_, i) => i !== rowIndex) } };
    });
  }

  function setRole(gameKey: string, side: "away" | "home", rowIndex: number, role: ScenarioRole | "") {
    setBuilderFlags((prev) => {
      const current = sidesFor(gameKey);
      const rows = current[side].map((row, i) => (i === rowIndex ? { role, positions: defaultPositionsForRole(role) } : row));
      return { ...prev, [gameKey]: { ...current, [side]: rows } };
    });
  }

  function togglePosition(gameKey: string, side: "away" | "home", rowIndex: number, position: string) {
    setBuilderFlags((prev) => {
      const current = sidesFor(gameKey);
      const rows = current[side].map((row, i) => {
        if (i !== rowIndex) return row;
        const positions = row.positions.includes(position)
          ? row.positions.filter((p) => p !== position)
          : [...row.positions, position];
        return { ...row, positions };
      });
      return { ...prev, [gameKey]: { ...current, [side]: rows } };
    });
  }

  function handleAddScenario() {
    const teamFlags = buildTeamFlags(games, builderFlags);
    if (!builderLabel.trim() || teamFlags.length === 0) return;
    setScenarios((prev) => [...prev, { label: builderLabel.trim(), team_flags: teamFlags }]);
    setBuilderLabel("");
    setBuilderFlags({});
  }

  function handleRemoveScenario(index: number) {
    setScenarios((prev) => prev.filter((_, i) => i !== index));
  }

  async function handleEvaluate() {
    if (scenarios.length === 0) return;
    setEvaluating(true);
    setEvaluateError(null);
    try {
      const result = await evaluateLineupScenarios(season, week, platform, contest, scenarios, minStackSize);
      setAnalysis(result);
    } catch (err) {
      setEvaluateError(err instanceof Error ? err.message : "Failed to evaluate scenarios");
    } finally {
      setEvaluating(false);
    }
  }

  const pendingTeamFlags = buildTeamFlags(games, builderFlags);

  return (
    <div className="lineup-scenarios">
      <CollapsibleHint
        title="About this tab"
        items={[
          "Upload a batch of lineups you already built in an external optimizer -- one row per lineup, DraftKings' own \"Player Name (ID)\" cell format.",
          "A scenario flags one or more teams. For each team, add one or more role rows -- pick the role you think it's playing this week (e.g. \"High scoring\" or \"Positive script\") and narrow it to specific depth-chart slots that actually benefit (e.g. just that team's starting RB, RB1).",
          "You can add multiple role rows to the SAME team within one scenario -- e.g. this team's RB1 for positive script AND its WR1/WR2 for pass funnel -- both are counted independently and both must clear the Min threshold.",
          "Position chips are depth-chart-specific (RB1 vs RB2, WR1 vs WR2 vs WR3, etc.), not just \"RB\"/\"WR\" -- each role pre-fills a sensible set of slots when you pick it, but you can edit the chips freely. Depth slots need this week's Depth Charts data retrieved to resolve.",
          "A lineup \"satisfies\" a scenario only when it rosters at least Min matching players for EVERY role row across every team flagged in that scenario.",
          "Player teams and depth slots are resolved by name against this week's DK salary file and depth chart -- upload/retrieve those first if you haven't. Names that don't match anything are listed below the results so you know they can't count toward any stack.",
          "This is pure stack-counting -- no fantasy-point projections are used anywhere in this tab.",
        ]}
      />

      <div className="lineup-scenarios-upload">
        <label className="player-pool-upload-label">
          <input type="file" accept=".csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </label>
        <button type="button" className="player-pool-save-button" disabled={!file || uploading} onClick={handleUpload}>
          {uploading ? "Uploading…" : "Upload lineups"}
        </button>
        {uploadMessage && <span className="hint">{uploadMessage}</span>}
        {uploadError && <span className="hint lineup-scenarios-error">{uploadError}</span>}
      </div>

      <div className="lineup-scenarios-builder">
        <h3>Build a scenario</h3>
        <input
          type="text"
          className="lineup-scenarios-label-input"
          placeholder="Scenario label, e.g. BUF/KC shootout"
          value={builderLabel}
          onChange={(e) => setBuilderLabel(e.target.value)}
        />
        {games.length === 0 && (
          <p className="hint">No games found -- upload this week's Schedule file and DK salary file first.</p>
        )}
        <div className="lineup-scenarios-game-rows">
          {games.map((game) => {
            const [away, home] = game.label.split(" @ ");
            const sides = sidesFor(game.key);
            return (
              <div key={game.key} className="lineup-scenarios-game-row">
                <span className="lineup-scenarios-game-label">{game.label}</span>
                <div className="lineup-scenarios-role-sides">
                  {(
                    [
                      ["away", away],
                      ["home", home],
                    ] as const
                  ).map(([side, teamName]) => (
                    <div key={side} className="lineup-scenarios-role-side">
                      <span className="lineup-scenarios-role-team-name">{teamName}</span>
                      <div className="lineup-scenarios-flag-rows">
                        {sides[side].map((selection, rowIndex) => (
                          <div key={rowIndex} className="lineup-scenarios-flag-row">
                            <div className="lineup-scenarios-flag-row-header">
                              <select
                                className="lineup-scenarios-role-select"
                                value={selection.role}
                                onChange={(e) => setRole(game.key, side, rowIndex, e.target.value as ScenarioRole | "")}
                              >
                                {ROLE_OPTIONS.map((opt) => (
                                  <option key={opt.value} value={opt.value}>
                                    {opt.label}
                                  </option>
                                ))}
                              </select>
                              <button
                                type="button"
                                className="lineup-scenarios-remove-role"
                                aria-label="Remove this role"
                                onClick={() => removeRow(game.key, side, rowIndex)}
                              >
                                ×
                              </button>
                            </div>
                            {selection.role && (
                              <div className="lineup-scenarios-position-chip-row">
                                {ALL_DEPTH_SLOTS.map((position) => (
                                  <button
                                    key={position}
                                    type="button"
                                    className={`chip${selection.positions.includes(position) ? " selected" : ""}`}
                                    aria-pressed={selection.positions.includes(position)}
                                    onClick={() => togglePosition(game.key, side, rowIndex, position)}
                                  >
                                    {position}
                                  </button>
                                ))}
                              </div>
                            )}
                          </div>
                        ))}
                        <button
                          type="button"
                          className="lineup-scenarios-add-role"
                          onClick={() => addRow(game.key, side)}
                        >
                          + Add role
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
        <button
          type="button"
          className="player-pool-save-button"
          disabled={!builderLabel.trim() || pendingTeamFlags.length === 0}
          onClick={handleAddScenario}
        >
          Add scenario
        </button>
      </div>

      {scenarios.length > 0 && (
        <div className="lineup-scenarios-list chip-row">
          {scenarios.map((scenario, i) => (
            <span key={i} className="player-chip">
              {scenario.label} (
              {scenario.team_flags
                .map((flag) => `${flag.team} ${flag.role}${flag.positions.length > 0 ? ` [${flag.positions.join("/")}]` : ""}`)
                .join(", ")}
              )
              <button
                type="button"
                className="player-chip-remove"
                aria-label={`Remove ${scenario.label}`}
                onClick={() => handleRemoveScenario(i)}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}

      <div className="lineup-scenarios-evaluate">
        <label className="lineup-scenarios-min-stack-label">
          Min players per team
          <input
            type="number"
            min={1}
            max={9}
            value={minStackSize}
            onChange={(e) => setMinStackSize(Math.max(1, Number(e.target.value) || 1))}
          />
        </label>
        <button
          type="button"
          className="player-pool-save-button"
          disabled={scenarios.length === 0 || evaluating}
          onClick={handleEvaluate}
        >
          {evaluating ? "Evaluating…" : "Evaluate"}
        </button>
        {evaluateError && <span className="hint lineup-scenarios-error">{evaluateError}</span>}
      </div>

      {analysis && (
        <div className="lineup-scenarios-results">
          {analysis.unresolved_player_names.length > 0 && (
            <p className="hint lineup-scenarios-unresolved">
              Couldn't match these players to this week's DK salary file (they won't count toward any team's stack):{" "}
              {analysis.unresolved_player_names.join(", ")}
            </p>
          )}
          <table className="lineup-scenarios-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Lineup</th>
                {analysis.results[0]?.matches.map((match, i) => <th key={i}>{match.label}</th>)}
              </tr>
            </thead>
            <tbody>
              {analysis.results.map((result) => (
                <tr key={result.lineup.index}>
                  <td>{result.lineup.index}</td>
                  <td className="lineup-scenarios-roster-cell">
                    {result.lineup.players.map((p) => `${p.roster_position} ${p.name}`).join(", ")}
                  </td>
                  {result.matches.map((match, i) => (
                    <td key={i}>
                      <span
                        className={`lineup-scenarios-badge${match.satisfied ? " satisfied" : " unsatisfied"}`}
                        title={match.team_stacks
                          .map((s) => `${s.team} (${s.role}${s.positions.length > 0 ? `, ${s.positions.join("/")}` : ""}): ${s.count}`)
                          .join(", ")}
                      >
                        {match.satisfied ? "✓" : "✗"}
                      </span>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
