# dfs-app frontend

React + TypeScript (Vite). Runs as its own dev server, separate from the
FastAPI backend -- see `../backend/main.py` for the CORS setup that allows this
origin (`http://localhost:5173` by default) to call the API directly.

## Setup

```bash
cd frontend
npm install
cp .env.example .env.local   # defaults are fine if the backend runs on :8000
```

## Run

Backend (from the repo root, in another terminal):

```bash
uvicorn backend.main:app --reload
```

Frontend:

```bash
npm run dev
```

Then open http://localhost:5173.

## What it does

Two tabs, switched with a simple in-app toggle (no routing/URLs):
**Compare Depth Charts** and **Usage Bump Players**. "Retrieve depth chart" lives in
the shared header above both tabs since a new snapshot is relevant to
either view.

- **Retrieve depth chart** -- triggers `POST /api/depth-charts/scrape` on the
  backend (a real scrape + a new saved snapshot), then refreshes whichever
  tab is active (and the other tab refetches next time you switch to it).

### Compare Depth Charts tab
- **Snapshot picker** -- two month-view calendars (From / To), each
  independently navigable and defaulting to the current month. Day boxes
  show only the day number -- no times. Click any day that has one or more
  scrapes and a modal opens listing its time(s), 12-hour (AM/PM), to pick
  from. Days with no scrapes are dimmed and not clickable. The two
  calendars' browsed months are locked together -- From can never be
  navigated past whatever month To is showing, and To can never be
  navigated before From's month (equal months are fine; only passing each
  other is blocked). Whichever
  snapshot is currently selected on one side is hidden as an option on the
  other side (so you can't pick the same snapshot for both From and To) --
  if that empties out a day entirely, that day becomes unselectable on the
  other calendar too. Plus a "Compare selected" button
  (`GET /api/depth-charts/diff?from=&to=`) and a "Compare last two" button
  (`GET /api/depth-charts/diff/latest`).
- **Filters** -- a row between the picker and the results with four
  pieces, all client-side over whatever the last comparison returned:
  - **Position filter** -- a dropdown defaulting to "All". Grouped presets
    (Fantasy, Offensive, Defensive, Special Teams -- these overlap on
    purpose) plus individual position-type breakdowns (Quarterbacks,
    Running Backs, Offensive Line, Defensive Backs, etc. -- see
    `src/positionFilters.ts` for the full list). Team-level changes
    (`defensive_formation`, no position) never match any filter, so they
    drop out whenever one is active.
  - **Status filter** -- multi-select chips, one per valid status code
    (`src/statusCodes.ts`). Matches a change's *current* status (e.g.
    picking "IR" shows players who are now IR, not players who used to be
    IR). Selecting more than one chip is an OR within the status filter;
    the status and position filters are AND'd together. Changes with no
    current status (removed players, team-level changes) never match once
    any status chip is selected.
  - **Position Depth filter** -- multi-select chips (`src/depthFilter.ts`),
    matching a change's *current* depth (same "current, not previous"
    convention as the Status filter). Nothing is checked before any
    comparison has run -- chips 1-13 plus a trailing `N/A` chip (covers
    rows with no current depth at all -- team-level changes and removed
    players) show as unchecked placeholders, since there's nothing to
    filter yet anyway. Once a comparison loads, the chip list itself is
    replaced by whichever depths actually appear in the results (could be
    fewer chips, more, or go past 13), and the selection auto-updates to
    1 through the deepest depth present, capped at 4 -- plus `N/A` if the
    comparison has any team-level changes or removed players. Every *new*
    comparison recomputes this from scratch, overwriting whatever the
    user had manually picked for the previous one; chips can still be
    freely toggled in between. Unlike the Position/Status filters, this
    one has no "empty = show everything" state: it's always active, so
    unchecking every chip shows zero results rather than falling back to
    unfiltered.
  - **Status key** -- a collapsed-by-default "Status key" toggle that
    expands to the full code -> meaning legend (IR = Injured Reserve,
    etc.).
- **Results** -- the heading shows the From/To pair as `MM-DD h:mm AM/PM →
  MM-DD h:mm AM/PM` (year added to both sides only when they fall in
  different years) and the count reflects whatever the active filters left
  visible. Changes are grouped by team, then by position within each team.
  Each row shows the player (or the team-level field, e.g.
  `defensive_formation`), which dimensions changed (`status`, `rank`,
  `other`), and the before/after values.

All diffing happens live on the backend on every request -- nothing is
cached or persisted between comparisons, so re-running the same comparison
always reflects the current files on disk.

### Usage Bump Players tab

Fetches `GET /api/opportunities/latest` on load (and whenever a new
snapshot is retrieved) -- who benefits from the *latest* depth chart's
current statuses, not a diff between two snapshots. The backend computes a
(fractional, not integer) `bump_score` per beneficiary and the reasons
behind it (`causes`) from three config files -- see the root README's
"Run" section and `backend/services/usage_bump/engine.py` for the full
curated-list-vs-position-role-fallback algorithm (the endpoint URL stays
`/api/opportunities/latest` -- a public API contract -- even though
everything else, backend package name through Pydantic model names and
JSON field names, is `usage_bump`/`bump` throughout); this page only
filters/sorts whatever that endpoint returns, client-side:

- **Team filter** -- multi-select chips, options pulled from whichever
  teams are actually in the response.
- **Position filter** -- multi-select chips, but restricted to offensive
  fantasy positions only (QB, RB, WR, TE -- `OFFENSIVE_FANTASY_POSITIONS`
  in `src/positionFilters.ts`), unlike the Compare Depth Charts tab's 13-preset
  position filter. This restriction holds even when nothing is checked
  (the chip row's "All" option only means "don't narrow further within
  QB/RB/WR/TE," not "show every position").
- **Position Depth filter** -- multi-select chips for the player's own
  rank (1-4 only, no "All" chip), defaulting to all four checked. This is
  a hard cap, same spirit as the position filter -- 5th-string-and-deeper
  never shows, even if every chip gets unchecked (that falls back to the
  same 1-4 range, not wider).
- **Min bump score** -- a number input, defaults to 1 (i.e. show anyone
  with any bump at all).
- **Sort by** -- Bump (high to low, default), Bump (low to high), Name,
  or Team.

Above the result rows, a plain header line labels the two things every
row shows: "Player" / "Bump Value".

Each result row shows the player, team + position/rank as a single label
(e.g. `RB2`), the bump score, and a comma-separated breakdown of causes
with no label prefix -- one entry per cause, each showing the teammate
who's out, their status, their own role label (position + depth-chart
rank), and the individual weight that cause contributed (e.g. "Emeka
Egbuka (Q) WR1: +2, Jalen McMillan (Q) WR2: +1, Cade Otton (Q) TE1: +1").
Rows sit flush against each other (no gap between them) so the list reads
as one continuous block rather than a stack of separated cards.

Clicking anywhere in that summary area -- or the "Details ▾" toggle below
it -- expands/collapses the same breakdown; both are just two ways to
reach the one piece of state. Expanding shows one section per cause -- the
literal player-out-settings.json lookup behind each contribution, not
just the resulting number:

- A header showing that cause's teammate, status, and their own role
  label instead of the weight (e.g. "Emeka Egbuka (Q) WR2") -- the weight
  itself is still visible in the one-line causes summary above the
  "Details" toggle, so it isn't repeated here.
- A source-rule caption, generated from the same live config data that
  drove the calculation (`UsageBumpCause.source`/`source_role_label`/
  `source_role_positions`): for a position-settings-resolved cause, the
  exact rule that matched (e.g. "Usage bump players by position: WR1,
  WR3, TE1, RB1" -- the role label itself already shows in the header
  just above, so it isn't repeated in this line); for a curated-list-
  resolved cause, "Usage bump player for {trigger}" instead, since there's no
  positional rule to show.
- A "Player out depth(s): ..." caption -- the exact combo that was looked
  up in `player-out-settings.json`'s `player_out_depths` field, in plain
  language rather than the raw JSON shape (`Player out depth(s): 0
  (nobody else in the list is out)`, or e.g. `Player out depth(s): 1, 3`).
- A table of that trigger's *entire* resolved usage-bump list
  (`usage_bump_list`) -- Depth / Value / Player, in that order, for
  every position in it, not just the one this row's player occupies, with
  the current player's own row highlighted. The Player column carries the
  name, status (in parens, only when out -- e.g. "Xavier Legette (Q)";
  healthy members just show their bare name), and role label all together
  (e.g. "Xavier Legette (Q) WR3") rather than a separate Position column.
  Depth and Value get narrow fixed-width columns since they only ever
  hold a short number, Player gets whatever width is left over, and the
  three columns have extra horizontal padding between them (extra
  whitespace between Depth and Value specifically, on top of that).

A final "Total" line sums all the causes' weights back to the bump score
shown in the row header.

## Mobile

The layout is responsive down to ~375px-wide phone screens (everything
above that keeps the wider desktop layout): the header stacks, the From/To
calendars and action buttons go full-width and stack vertically, and the
diff rows (player / change types / values) stack instead of trying to fit
three columns in a narrow row. Buttons, the day cells, and the time-picker
modal all use ~44px touch targets.

The app is also set up as an installable PWA (`public/manifest.json` +
`icon-192.png`/`icon-512.png`, plus the manifest link and mobile meta tags
in `index.html`) so it can be added to a phone's home screen and opened in
standalone mode. It's just the same React app wrapped -- there's no
separate mobile codebase to keep in sync.

## Project layout

```
frontend/
  public/
    manifest.json              PWA manifest (name, icons, theme color)
    icon-192.png, icon-512.png PWA/home-screen icons
  src/
    types.ts                  Mirrors the backend's Pydantic schemas by hand
    api.ts                    Thin fetch wrapper around the backend endpoints
    snapshotId.ts              Parses/formats "YYYY-MM-DD_HHMM" snapshot ids
                                (date/time parts, AM/PM, from/to range label)
    positionFilters.ts         13 position filter presets (groups + individual),
                                plus positionsForFilters() for multi-select union
    statusCodes.ts             The 11 valid status codes + descriptions
    depthFilter.ts              Compare Depth Charts tab's Position Depth filter: builds the
                                 chip list (1-4 + placeholder 5-13 before a
                                 comparison runs, replaced by data-driven extras
                                 after), the default (1-4 + N/A) selection, and
                                 the current-depth match predicate
    App.tsx                   Just the header, the Compare Depth Charts/Usage Bump
                               Players tab toggle, and the shared refreshSignal counter
    components/
      CompareView.tsx           Everything the Compare Depth Charts tab used to be in App.tsx:
                                 snapshots, selection, diff result, position/status/
                                 depth filters
      UsageBumpView.tsx         Usage Bump Players tab: fetches
                                 /api/opportunities/latest, applies team/position/
                                 min-score filters and sort client-side
      RetrieveButton.tsx        Triggers a scrape
      SnapshotPicker.tsx        From/To MonthCalendars + compare actions
      MonthCalendar.tsx         Custom month grid; days show only a number,
                                 click opens a modal to pick the time; hides
                                 the other calendar's current selection
      PositionFilterSelect.tsx  Position filter dropdown (Compare Depth Charts tab, single-select)
      StatusFilter.tsx          Status filter chips (Compare Depth Charts tab, multi-select)
      StatusKey.tsx              Collapsible status code -> meaning legend
      ChipMultiSelect.tsx        Generic multi-select chip row (team/position/depth
                                 filters on the Usage Bump Players tab, and now the
                                 Compare Depth Charts tab's Position Depth filter too). Leads with
                                 an "All" chip by default (clears the selection);
                                 showAllOption={false} drops it for closed/always-on
                                 sets like both tabs' Position Depth filters
      DiffResults.tsx           Groups changes by team, then position;
                                 applies the position + status + depth filters
```
