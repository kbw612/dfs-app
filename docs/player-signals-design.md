# Player Signals design

The Player Signals tab lists every slate player with plain-language reasons (chips) to
include or avoid him. Net signals = positive chips minus negative chips. Usage rules use
the last X completed weeks (default 5); opponent-history rules default to the same last X weeks, with a Season option.
Code: `backend/services/player_signals/` (engine, thresholds), `backend/api/player_signals/`,
`frontend/src/components/PlayerSignalsView.tsx`.

## Future data enhancements

Needs new data, so we need your call on each:

- **Inside-10 carries and targets:** appears in about half of JM's bullets. Do the logs have red-zone detail? If not, we skip it or add a source.
- **EPA per target, per rush, and per dropback:** not in the app today.
- **Pass rate over expected (PROE):** not in the app.
- **Air-yards share and downfield rate over expected (DROE):** not in the app.
- **Opponent rate of 20+ yard completions and 20+ air-yard throws:** not in the app.

Possible sources to check: the OWS Stat Finder page or a StatRankings export.

Other rules not built yet: salary change versus last week, and teammate-returning chips
(for example a starting back returning from injury).
