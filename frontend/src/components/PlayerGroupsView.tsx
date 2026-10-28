import { useEffect, useRef, useState } from "react";
import {
  exportPlayerGroups,
  fetchGroupPool,
  fetchPlayerGroups,
  importPlayerGroups,
  savePlayerGroups,
} from "../api";
import { ConfirmDialog } from "./ConfirmDialog";
import type { GroupGameChip, GroupSummary, PlayerGroup, PoolPlayer } from "../types";

interface PlayerGroupsViewProps {
  season: number;
  week: number;
  platform: string;
  contest: string;
}

const POSITIONS = ["ALL", "QB", "RB", "WR", "TE", "DST"];

// Plain groups (what the backend saves) from the editable list.
function plain(groups: PlayerGroup[]): PlayerGroup[] {
  return groups.map((g) => ({
    name: g.name,
    pct: g.pct,
    min: g.min,
    max: g.max,
    players: g.players.map((p) => ({ id: p.id, name: p.name, anchor: p.anchor })),
  }));
}

export function PlayerGroupsView({ season, week, platform, contest }: PlayerGroupsViewProps) {
  const [groups, setGroups] = useState<PlayerGroup[]>([]);
  const [summaries, setSummaries] = useState<GroupSummary[]>([]);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [selected, setSelected] = useState(0);
  const [newName, setNewName] = useState("");
  const [games, setGames] = useState<GroupGameChip[]>([]);
  const [gameKeys, setGameKeys] = useState<string[]>([]);
  const [position, setPosition] = useState("ALL");
  const [q, setQ] = useState("");
  const [myPool, setMyPool] = useState(false);
  const [myPoolCount, setMyPoolCount] = useState(0);
  const [hideMin, setHideMin] = useState(true);
  const [minSalaries, setMinSalaries] = useState<Record<string, number>>({});
  const [pool, setPool] = useState<PoolPlayer[]>([]);
  const [replaceAll, setReplaceAll] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<number | null>(null);
  const [saveState, setSaveState] = useState<"saved" | "saving" | "error">("saved");
  const dragFrom = useRef<number | null>(null);
  const [overIndex, setOverIndex] = useState<number | null>(null);
  const loaded = useRef(false);
  const saveTimer = useRef<number | null>(null);

  const apply = (state: { groups: GroupSummary[]; warnings: string[] }, replaceEditable: boolean) => {
    setSummaries(state.groups);
    setWarnings(state.warnings);
    if (replaceEditable) setGroups(plain(state.groups));
  };

  // Load saved groups when the week/contest changes.
  useEffect(() => {
    loaded.current = false;
    setError(null);
    fetchPlayerGroups(season, week, platform, contest)
      .then((s) => {
        apply(s, true);
        setSelected(0);
        loaded.current = true;
      })
      .catch((e) => setError(String(e.message ?? e)));
  }, [season, week, platform, contest]);

  // Pool for the chips/search (salary high to low, filtered by the backend).
  useEffect(() => {
    fetchGroupPool(season, week, platform, contest, gameKeys, position, q, myPool, hideMin)
      .then((r) => {
        setPool(r.players);
        setGames(r.games);
        setMyPoolCount(r.my_pool_count);
        setMinSalaries(r.min_salaries);
      })
      .catch(() => undefined);
  }, [season, week, platform, contest, gameKeys, position, q, myPool, hideMin]);

  // Edits save themselves a moment after the last change.
  const edit = (next: PlayerGroup[], nextSelected = selected) => {
    setGroups(next);
    setSelected(nextSelected);
    setSaveState("saving");
    if (saveTimer.current) window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => {
      savePlayerGroups(season, week, platform, contest, plain(next))
        .then((s) => {
          apply(s, false);
          setSaveState("saved");
          setError(null);
        })
        .catch((e) => {
          setSaveState("error");
          setError(String(e.message ?? e));
        });
    }, 400);
  };

  const current = groups[selected];
  const update = (patch: Partial<PlayerGroup>) => {
    if (!current) return;
    edit(groups.map((g, i) => (i === selected ? { ...g, ...patch } : g)));
  };

  const addGroup = () => {
    const name = newName.trim();
    if (!name) return;
    edit([...groups, { name, pct: 100, min: 1, max: 9, players: [] }], groups.length);
    setNewName("");
  };

  const addPlayer = (p: PoolPlayer) => {
    if (!current || current.players.some((x) => x.id === p.id)) return;
    update({ players: [...current.players, { id: p.id, name: p.name, anchor: false }] });
  };

  const drop = (to: number) => {
    const from = dragFrom.current;
    dragFrom.current = null;
    setOverIndex(null);
    if (from === null || from === to) return;
    const next = groups.slice();
    const [moved] = next.splice(from, 1);
    next.splice(to, 0, moved);
    edit(next, to);
  };

  // Adds every player currently shown in the list (whatever the game, position,
  // My Player Pool and search filters) that isn't already in the group.
  const addAllShown = () => {
    if (!current) return;
    const fresh = pool.filter((p) => !current.players.some((x) => x.id === p.id));
    if (fresh.length === 0) return;
    update({ players: [...current.players, ...fresh.map((p) => ({ id: p.id, name: p.name, anchor: false }))] });
  };

  const upload = async (file: File | undefined) => {
    if (!file) return;
    try {
      const s = await importPlayerGroups(season, week, platform, contest, file, replaceAll);
      apply(s, true);
      setSelected(0);
      setError(null);
    } catch (e) {
      setError(String((e as Error).message ?? e));
    }
  };

  const exportCsv = async () => {
    try {
      const r = await exportPlayerGroups(week, contest, plain(groups));
      const url = URL.createObjectURL(new Blob([r.csv], { type: "text/csv" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = r.filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(String((e as Error).message ?? e));
    }
  };

  const inGroup = new Set(current?.players.map((p) => p.id));
  const notYetAdded = pool.filter((p) => !inGroup.has(p.id)).length;
  const toggleGame = (key: string) => setGameKeys(gameKeys.includes(key) ? gameKeys.filter((k) => k !== key) : [...gameKeys, key]);

  return (
    <div className="player-groups">
      <h2>Player Groups</h2>
      <div className="pg-bar">
        <input type="file" accept=".csv" onChange={(e) => upload(e.target.files?.[0])} />
        <label>
          <input type="checkbox" checked={replaceAll} onChange={(e) => setReplaceAll(e.target.checked)} /> Replace all groups
        </label>
        <span className="pg-spacer" />
        <span className="pg-hint">{saveState === "saving" ? "Saving…" : saveState === "saved" ? "Saved" : "Not saved"}</span>
        <button type="button" disabled={groups.length === 0} onClick={exportCsv}>
          Export groups CSV
        </button>
      </div>
      {error && <p className="pg-error">{error}</p>}
      {warnings.map((w) => (
        <p key={w} className="pg-warning">
          {w}
        </p>
      ))}

      <div className="pg-cols">
        <div>
          <div className="pg-list">
            {groups.map((g, i) => (
              <div
                key={`${g.name}-${i}`}
                className={`pg-item${i === selected ? " selected" : ""}${overIndex === i ? " over" : ""}`}
                onClick={() => setSelected(i)}
                onDragOver={(e) => {
                  if (dragFrom.current === null) return;
                  e.preventDefault();
                  setOverIndex(i);
                }}
                onDrop={(e) => {
                  e.preventDefault();
                  drop(i);
                }}
              >
                <span
                  className="pg-handle"
                  draggable
                  title="Drag to reorder"
                  onDragStart={(e) => {
                    dragFrom.current = i;
                    e.dataTransfer.effectAllowed = "move";
                    e.dataTransfer.setData("text/plain", String(i));
                  }}
                  onDragEnd={() => {
                    dragFrom.current = null;
                    setOverIndex(null);
                  }}
                >
                  ⋮⋮
                </span>
                <span className="pg-name">
                  {i + 1}. {g.name}
                </span>
                <span className="pg-hint">{g.players.length}</span>
                <button
                  type="button"
                  className="secondary pg-x"
                  aria-label={`Delete ${g.name}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    setPendingDelete(i);
                  }}
                >
                  ×
                </button>
              </div>
            ))}
            {groups.length === 0 && <div className="pg-empty">No groups yet. Name one below.</div>}
          </div>
          <div className="pg-new">
            <input
              placeholder="Block name"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addGroup()}
            />
            <button type="button" disabled={!newName.trim()} onClick={addGroup}>
              Add group
            </button>
          </div>
        </div>

        <div className="pg-editor">
          {current ? (
            <>
              <div className="pg-bar">
                <input value={current.name} onChange={(e) => update({ name: e.target.value })} className="pg-name-input" aria-label="Group name" />
                <label>
                  Pct <input type="number" min={0} max={100} value={current.pct} onChange={(e) => update({ pct: Number(e.target.value) })} />
                </label>
                <label>
                  Min <input type="number" min={0} value={current.min} onChange={(e) => update({ min: Number(e.target.value) })} />
                </label>
                <label>
                  Max <input type="number" min={0} value={current.max} onChange={(e) => update({ max: Number(e.target.value) })} />
                </label>
              </div>
              <table className="pg-table">
                <thead>
                  <tr>
                    <th>Anchor</th>
                    <th>Remove</th>
                    <th className="pg-left">Player</th>
                    <th>Salary</th>
                    <th>Pos</th>
                  </tr>
                </thead>
                <tbody>
                  {current.players.map((p) => {
                    // The filtered pool has him, or the backend's last summary does.
                    const info =
                      pool.find((x) => x.id === p.id) ?? summaries[selected]?.players.find((x) => x.id === p.id);
                    return (
                      <tr key={p.id}>
                        <td>
                          <button
                            type="button"
                            className={p.anchor ? "" : "secondary"}
                            onClick={() => update({ players: current.players.map((x) => (x.id === p.id ? { ...x, anchor: !x.anchor } : x)) })}
                          >
                            {p.anchor ? "Locked" : "Lock"}
                          </button>
                        </td>
                        <td>
                          <button type="button" className="secondary" onClick={() => update({ players: current.players.filter((x) => x.id !== p.id) })}>
                            Remove
                          </button>
                        </td>
                        <td className="pg-left">{p.name}</td>
                        <td>{info?.salary ?? ""}</td>
                        <td>{info?.position ?? ""}</td>
                      </tr>
                    );
                  })}
                  {current.players.length === 0 && (
                    <tr>
                      <td colSpan={5} className="pg-left pg-hint">
                        No players yet. Add some from the list below.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </>
          ) : (
            <p className="pg-hint">Add a group to start.</p>
          )}
        </div>
      </div>

      <h3>Add players{current ? ` to ${current.name}` : ""}</h3>
      <div className="pg-bar">
        <span className="pg-hint">Games</span>
        <button type="button" className={gameKeys.length === 0 ? "" : "secondary"} onClick={() => setGameKeys([])}>
          All
        </button>
        {games.map((g) => (
          <button key={g.key} type="button" className={gameKeys.includes(g.key) ? "" : "secondary"} onClick={() => toggleGame(g.key)}>
            {g.label}
          </button>
        ))}
      </div>
      <div className="pg-bar">
        <span className="pg-hint">Position</span>
        {POSITIONS.map((p) => (
          <button key={p} type="button" className={p === position ? "" : "secondary"} onClick={() => setPosition(p)}>
            {p === "ALL" ? "All" : p}
          </button>
        ))}
        <button
          type="button"
          className={hideMin ? "" : "secondary"}
          onClick={() => setHideMin(!hideMin)}
          title={`Hides players priced at their position's minimum: ${Object.entries(minSalaries)
            .map(([pos, sal]) => `${pos} $${sal}`)
            .join(", ")}`}
        >
          Hide min salary
        </button>
        <button
          type="button"
          className={myPool ? "" : "secondary"}
          onClick={() => setMyPool(!myPool)}
          title="Only players you added in My Player Pool"
        >
          My Player Pool ({myPoolCount})
        </button>
        <input placeholder="Search players" value={q} onChange={(e) => setQ(e.target.value)} />
        <span className="pg-spacer" />
        <button type="button" disabled={!current || notYetAdded === 0} onClick={addAllShown}>
          Add all {notYetAdded} shown{current ? ` to ${current.name}` : ""}
        </button>
      </div>
      <div className="pg-table-wrap">
        <table className="pg-table">
          <thead>
            <tr>
              <th>Add</th>
              <th className="pg-left">Player</th>
              <th>Salary</th>
              <th>Pos</th>
              <th>Team</th>
              <th>Opp</th>
            </tr>
          </thead>
          <tbody>
            {pool.length === 0 && (
              <tr>
                <td colSpan={6} className="pg-left pg-hint">
                  {myPool && myPoolCount === 0
                    ? "No players in My Player Pool for this week."
                    : "No players match these filters."}
                </td>
              </tr>
            )}
            {pool.map((p) => (
              <tr key={p.id}>
                <td>
                  <button type="button" disabled={!current || inGroup.has(p.id)} onClick={() => addPlayer(p)}>
                    {inGroup.has(p.id) ? "Added" : "+"}
                  </button>
                </td>
                <td className="pg-left">{p.name}</td>
                <td>{p.salary}</td>
                <td>{p.position}</td>
                <td>{p.team}</td>
                <td>{p.opponent}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3>Group previews (export order)</h3>
      <div className="pg-blocks">
        {summaries.map((g, i) => (
          <div key={`${g.name}-${i}`} className="pg-block">
            <h4>
              {i + 1}. {g.name}
            </h4>
            <p className="pg-hint">
              Pct {g.pct}% · Min {g.min} · Max {g.max} · {g.player_count} players · ${g.salary_total.toLocaleString()}
            </p>
            {g.players.map((p) => (
              <div key={p.id} className="pg-block-player">
                <span>
                  {p.name}
                  {p.anchor ? " (anchor)" : ""}
                </span>
              </div>
            ))}
          </div>
        ))}
      </div>

      {pendingDelete !== null && groups[pendingDelete] && (
        <ConfirmDialog
          message={`Delete group "${groups[pendingDelete].name}" and its ${groups[pendingDelete].players.length} players? The players stay in the list and can be added again.`}
          confirmLabel="Delete"
          onConfirm={() => {
            const i = pendingDelete;
            setPendingDelete(null);
            edit(groups.filter((_, k) => k !== i), Math.max(0, Math.min(selected, groups.length - 2)));
          }}
          onCancel={() => setPendingDelete(null)}
        />
      )}
    </div>
  );
}
