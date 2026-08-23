# dfs-app

Local-first implementation of Section 2 of the design doc (Automated Depth
Chart & Injury Monitoring). This slice covers the scrape + diff pipeline:

```
scrape() -> build_json() -> enrich_team_abbrev() -> enrich_defensive_formation() -> save_snapshot()
```

Diffing is a separate, on-demand concern (see below) -- it's no longer part
of the scrape pipeline itself. There's also an `opportunities` resource
(`GET /api/opportunities/latest`) that computes, from the latest snapshot
alone, which players benefit when a teammate is out. A `frontend/` React +
TypeScript app (own dev server) sits on top of this API -- see
`frontend/README.md` to run it. Digest and a bundled dashboard are **not**
built yet.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # defaults are fine as-is
```

## Run

```bash
uvicorn backend.main:app --reload
```

Then trigger a scrape manually (Phase 1 is manual-only, per the design doc --
no scheduler yet):

```bash
curl -X POST http://127.0.0.1:8000/api/depth-charts/scrape
```

This writes a new file to `data/snapshots/depth_chart_{date}_{time}.json`
and returns a summary (path, team count, message counts) -- no diffing
happens here anymore.

See what's on disk to compare:

```bash
curl http://127.0.0.1:8000/api/depth-charts/snapshots
```

Lists every saved snapshot (id, scraped_at, team_count), newest first. The
`id` (e.g. `2026-08-14_0800`) is what you pass to the diff endpoints below.

Diff the two most recently saved snapshots:

```bash
curl http://127.0.0.1:8000/api/depth-charts/diff/latest
```

Diff any two snapshots by id:

```bash
curl "http://127.0.0.1:8000/api/depth-charts/diff?from=2026-08-13_0800&to=2026-08-14_0800"
```

Both diff endpoints compute `generate_diff()` live, on request -- nothing
is pre-computed or persisted (there's no `changes_*.jsonl` file anymore).
Snapshots are kept forever and diffing is cheap, so any pair -- including
"the last two" -- is always recomputed fresh rather than read back from a
saved file. `/diff/latest` 404s until at least two snapshots exist;
`/diff?from=&to=` 404s if either id doesn't match a saved snapshot.

Or skip curl entirely and use the frontend -- see `frontend/README.md`.

See who benefits if a player is out, based on the latest snapshot only
(not a diff between two):

```bash
curl http://127.0.0.1:8000/api/opportunities/latest
```

Every player with a non-null status (all 11 codes count, not just injury
ones) is a "trigger." Each trigger's usage-bump list -- who could benefit
from *their* absence -- comes from one of two config files, checked in
priority order:

1. `config/usage-bump-players.json` -- a curated, per-team, named-player
   list (e.g. if Jalen Coker is out, credit these specific WRs, in this
   order).
2. `config/usage-bump-position-settings.json` -- a universal (not
   per-team) fallback keyed by role label (position + real depth-chart
   rank, e.g. `"RB1"`), mapping to a list of *other* role labels that
   benefit -- which can span positions (RB1 going down can bump WRs and a
   TE, not just the other RBs). Each role label gets resolved to an
   actual player via that specific team's depth chart. A trigger whose
   role has no entry here, and no curated entry either, produces zero
   bump for anyone -- there's no third, generic fallback.

Either way the list is capped at 5 names (unresolved/off-roster names are
dropped first, so the cap always lands on 5 usable ones). Scoring comes
from a third file, `config/player-out-settings.json`: the trigger itself
is always out and never scorable, but the *rest* of its list can also
have members out, so the engine checks every list member's current status
and looks up the exact matching combination (a fractional score per list
position, not a flat +1) -- if that specific combination isn't in the
file, that trigger contributes nothing, no partial-credit guessing.
Contributions from different triggers landing on the same beneficiary
stack. Only players with a `bump_score > 0` are returned, and a
beneficiary must themselves be healthy. 404s until at least one snapshot
exists. See `backend/services/usage_bump/engine.py` for the full algorithm
(worth reading -- the three-file interaction is the whole point) and
`backend/schemas/usage_bump/usage_bump.py` for the response shape.

Each `UsageBumpCause` also carries the exact matrix lookup behind its
`weight`: its own `position`/`rank` (the trigger's real role label, e.g.
"WR2" -- same shape as `UsageBump.position`/`rank`); `player_out_depths`
(the combo key that matched in `player-out-settings.json` -- named to
match that file's own field, and `[0]` is the sentinel for "nobody else in
the list is out"); `usage_bump_list` (the trigger's whole resolved list
-- every position's player name, their own real position/rank, their
current status, and that matched row's weight for them -- not just the
position this particular beneficiary occupies); and
`source`/`source_role_label`/`source_role_positions` (whether this
trigger's list came from the curated file or the position-settings
fallback, and if the latter, the exact role label and raw
`usageBumpPositions` list that were looked up). This is what lets the
frontend show the literal config/scoring-matrix data behind a number
instead of just the number.

## Tests

```bash
pytest
```

Covers `extract_injury_status`, `parse_teams` (against a saved HTML fixture,
no network needed), `compute_defensive_formation`, both enrichment steps'
partial-failure behavior (one bad team_abbrev match doesn't block the rest
of the run), `generate_diff()` (matching, merging multiple change types onto
one record per player, team-level `defensive_formation` changes), the
snapshot repository's save/load/list/find-by-id helpers, `compute_usage_bumps()`
(curated-list scoring, position-settings fallback and role-label resolution,
curated-takes-priority semantics, unresolvable/off-roster names being
dropped, the 5-position cap, unconfigured combos producing zero, additive
stacking across triggers, sort order), and all three usage-bump config
loaders (`usage_bump_players_repo.py`, `position_settings_repo.py`,
`scoring_matrix_repo.py`).

## Project layout

Organized by layer first (`api` -> `services` -> `repositories` -> `schemas`),
then by resource within each layer. `depth_charts` and `usage_bump` are
the two resources today; adding another means dropping its own subpackage
next to these in each layer -- nothing existing moves. (The `usage_bump`
resource's *URL* stays `/api/opportunities` -- that's a public API contract,
separate from the internal package name.)

```
backend/
  main.py                      FastAPI app entrypoint. Mounts every resource's
                                router under "/api" (depth_charts under
                                "/api/depth-charts", usage_bump under
                                "/api/opportunities"); /health stays unprefixed
                                at the root since it's app-level, not a resource.
                                CORS opened up for the frontend's dev server origin.
  config.py                     Settings (env vars, file paths, source URL, frontend
                                 origin, the three usage-bump config paths)
  schemas/
    depth_charts/
      snapshot.py                Pydantic models: Player, Team, Message, Snapshot
      change.py                  Pydantic model: Change
    usage_bump/
      usage_bump.py               Pydantic models: UsageBumpCause, UsageBump
                                   (bump_score/weight are floats, not counts)
  services/
    depth_charts/
      scraper.py                 Step 1: scrape() + build_json()
      enrich.py                  Steps 2-3: enrich_team_abbrev(), enrich_defensive_formation()
      diff.py                    generate_diff() -- compares two snapshots, called live
                                  by the API, not part of the scrape pipeline
    usage_bump/
      engine.py                   compute_usage_bumps() -- derived analysis over a
                                   single (the latest) snapshot, not a diff. Read this
                                   file's docstring first -- it explains how the three
                                   config files below combine.
  repositories/
    depth_charts/
      snapshot_repo.py           save/load/list/find_by_id snapshot (local disk for now)
    usage_bump/
      usage_bump_players_repo.py    load_usage_bump_players() -- parses
                                     config/usage-bump-players.json
      position_settings_repo.py     load_usage_bump_position_settings() -- parses
                                     config/usage-bump-position-settings.json
      scoring_matrix_repo.py        load_bump_matrix() -- parses
                                     config/player-out-settings.json
  api/
    depth_charts/
      __init__.py                 Combines scrape.py + diff.py + snapshots.py under
                                   prefix "/depth-charts"
      scrape.py                   POST /scrape, orchestrates the pipeline (no diffing)
      diff.py                     GET /diff/latest, GET /diff?from=&to= -- both compute
                                   live; more diff-shaped endpoints can live here later
      snapshots.py                GET /snapshots -- lists every saved snapshot
    usage_bump/
      __init__.py                 Combines latest.py under prefix "/opportunities"
      latest.py                    GET /latest -- loads the latest snapshot + all three
                                    config files, computes compute_usage_bumps() live
config/
  team-info.csv                      Full Name -> abbreviation lookup (real content,
                                      pulled from your kbw612/Fantasy GitHub repo at
                                      scaffold time)
  usage-bump-players.json            Curated per-team, named-player usage-bump lists
                                      ({"name": "Jalen Coker", "moreUsagePlayers": [...]})
                                      -- highest priority, sparse by design
  usage-bump-position-settings.json  Universal (not per-team) role-label fallback
                                      ({"settings": [{"outPosition": "RB1",
                                      "usageBumpPositions": ["RB2", "WR1", ...]}]}) --
                                      used when a player has no curated entry; also
                                      sparse, only QB1/RB1/RB2/WR1/WR2/WR3/TE1 defined
                                      so far
  player-out-settings.json           The scoring matrix shared by both files above --
                                      given which list positions are also out, what
                                      bump each remaining healthy position gets.
                                      `player_out_depths: [0]` is the sentinel for
                                      "just the trigger is out, nothing else in its
                                      list is"
frontend/                      React + TypeScript app (own dev server, Vite)
                                -- see frontend/README.md
tests/
  fixtures/sample_depth_chart.html   Saved HTML so scraper tests don't hit the live site
  test_scraper.py
  test_enrich.py
  test_diff.py
  test_snapshot_repo.py
  test_usage_bump_engine.py
  test_usage_bump_players_repo.py
  test_position_settings_repo.py
  test_scoring_matrix_repo.py
data/
  snapshots/                   Created on first run; every scrape kept indefinitely
```

## What's deliberately not built yet

- `/digest` endpoint and digest records
- `GET /` dashboard bundled into this app
- `player_id` / player registry (explicitly deferred in the design doc)
- Cloud deployment (Phase 2 -- GCS, Cloud Scheduler, OIDC)
