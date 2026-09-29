import { useEffect, useRef, useState } from "react";
import "./App.css";
import { fetchCurrentWeek, fetchPlatformSettings, saveCurrentWeek, savePlatformSettings } from "./api";
import { BoomBustView } from "./components/BoomBustView";
import { CompareView } from "./components/CompareView";
import { ConfirmDialog } from "./components/ConfirmDialog";
import { ContestResultsView } from "./components/ContestResultsView";
import { DkPlayersView } from "./components/DkPlayersView";
import { DstTrendsView } from "./components/DstTrendsView";
import { GameLogsAgainstView } from "./components/GameLogsAgainstView";
import { GameLogsView } from "./components/GameLogsView";
import { GamePreviewView } from "./components/GamePreviewView";
import { HeaderSettingsPopover } from "./components/HeaderSettingsPopover";
import { MultipliersView } from "./components/MultipliersView";
import { MyPlayerPoolView } from "./components/MyPlayerPoolView";
import { OwnershipSummaryView } from "./components/OwnershipSummaryView";
import { OwnershipView } from "./components/OwnershipView";
import { PlayerPoolView } from "./components/PlayerPoolView";
import { SalaryBlocksView } from "./components/SalaryBlocksView";
import { SettingsView } from "./components/SettingsView";
import { UsageBumpPlayersView } from "./components/UsageBumpPlayersView";
import { UsageBumpView } from "./components/UsageBumpView";
import { DepthChartsView } from "./components/DepthChartsView";
import { InjuryReportView } from "./components/InjuryReportView";
import { LineupScenariosView } from "./components/LineupScenariosView";
import { VegasLinesView } from "./components/VegasLinesView";
import { WeatherView } from "./components/WeatherView";
import { BUILD_TIME, FRONTEND_VERSION } from "./version";

type View =
  | "settings"
  | "compare"
  | "depthCharts"
  | "injuryReport"
  | "bump"
  | "ownership"
  | "ownershipSummary"
  | "salaryBlocks"
  | "playerPool"
  | "vegasLines"
  | "weather"
  | "myPlayerPool"
  | "boomBust"
  | "contestResults"
  | "dkPlayers"
  | "gameLogs"
  | "gameLogsAgainst"
  | "multipliers"
  | "dstTrends"
  | "gamePreview"
  | "usageBumpPlayers"
  | "lineupScenarios";

// How long to wait after the last edit before persisting season/week to
// the backend (see backend/api/current_week) -- avoids a PUT on every
// keystroke while the number input is being typed into.
const CURRENT_WEEK_SAVE_DEBOUNCE_MS = 500;

function App() {
  const [view, setView] = useState<View>("settings");
  // Bumped on every successful scrape so whichever view isn't currently
  // mounted still refetches next time it's shown, and the currently
  // mounted one refetches immediately.
  const [refreshSignal, setRefreshSignal] = useState(0);

  // Fed by UsageBumpPlayersView's onDirtyChange -- true whenever it has an
  // edit that hasn't been Saved yet. `pendingView` holds the tab the
  // person clicked while dirty, so requestViewChange can ask via
  // ConfirmDialog before actually switching rather than silently
  // discarding the edit (see the tab buttons below, which all route
  // through requestViewChange instead of calling setView directly).
  const [usageBumpPlayersDirty, setUsageBumpPlayersDirty] = useState(false);
  const [pendingView, setPendingView] = useState<View | null>(null);

  function requestViewChange(next: View) {
    if (next === view) return;
    if (view === "usageBumpPlayers" && usageBumpPlayersDirty) {
      setPendingView(next);
      return;
    }
    setView(next);
  }

  // The single (season, week) pointer shared by every weekly tab
  // (Ownership, Salary Blocks, Player Pool) -- one control here instead of
  // each tab keeping its own copy, persisted server-side (see
  // backend/api/current_week) so it's the same value next time the app
  // opens, not just within one browser's localStorage. Defaults to the
  // current calendar year/week 1 until the initial GET resolves.
  const [season, setSeason] = useState(new Date().getFullYear());
  const [week, setWeek] = useState(1);
  const weekLoadedRef = useRef(false);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // The single (platform, contest) pointer shared by every tab that reads
  // the Salary File or Contest Standings file (Salary Blocks, Player
  // Rankings, My Player Pool, Boom/Bust, Contest Results, DK Players) or
  // the Settings tab's own upload widgets -- set via the Settings tab's
  // top panel, persisted server-side (see backend/api/platform_settings)
  // the same way season/week is, but scoped per season now (see
  // backend/schemas/platform_settings/platform_settings.py) -- switching
  // Season in Settings loads whichever platform/contest was last saved
  // for that season. Only "DraftKings" has a real file format behind it
  // today; "Classic Main" and "All Games" each resolve to their own
  // independent Salary File/Contest Standings file (see
  // backend/services/platform_settings/prefix.py's contest_slug()
  // -- SettingsView.tsx's CONTEST_OPTIONS).
  const [platform, setPlatform] = useState("DraftKings");
  const [contest, setContest] = useState("Classic Main");
  const platformLoadedRef = useRef(false);

  useEffect(() => {
    // Chained rather than fired in parallel with the platform-settings
    // fetch below -- Platform Settings needs a real season to look up,
    // and `season` state above starts as a placeholder (today's calendar
    // year) until this resolves, so fetching platform settings has to
    // wait for cw.season specifically rather than racing the state update.
    fetchCurrentWeek()
      .then((cw) => {
        setSeason(cw.season);
        setWeek(cw.week);
        return fetchPlatformSettings(cw.season);
      })
      .then((ps) => {
        setPlatform(ps.platform);
        setContest(ps.contest);
      })
      .catch(() => {
        // Best-effort -- falls back to the in-memory defaults above.
      })
      .finally(() => {
        weekLoadedRef.current = true;
        platformLoadedRef.current = true;
      });
  }, []);

  useEffect(() => {
    // Skip the save that would otherwise fire the moment the initial GET
    // above resolves and calls setSeason/setWeek -- that's an echo of what
    // the backend just told us, not a real edit.
    if (!weekLoadedRef.current) return;
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => {
      saveCurrentWeek({ season, week }).catch(() => {
        // Best-effort -- a failed save just means the next app load falls
        // back to whatever was last persisted; the current session still
        // has the right value in memory either way.
      });
    }, CURRENT_WEEK_SAVE_DEBOUNCE_MS);
    return () => {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    };
  }, [season, week]);

  useEffect(() => {
    // Re-fetch platform settings whenever season changes *after* the
    // initial load above already resolved -- covers editing Season
    // directly in Settings, since each season can have its own saved
    // platform/contest now. Guarded on platformLoadedRef (not
    // weekLoadedRef) so this doesn't double-fire right behind the initial
    // effect's own chained fetch: that ref only flips true once the
    // initial chain's fetchPlatformSettings call has already resolved.
    if (!platformLoadedRef.current) return;
    fetchPlatformSettings(season)
      .then((ps) => {
        setPlatform(ps.platform);
        setContest(ps.contest);
      })
      .catch(() => {
        // Best-effort, same reasoning as the current-week save above.
      });
  }, [season]);

  useEffect(() => {
    // Same echo-skip as season/week above. Chip selections are discrete
    // clicks, not continuous typing, so this saves immediately rather
    // than debouncing. Deliberately NOT keyed on `season` -- switching
    // season alone shouldn't immediately re-save whatever platform/contest
    // happened to be in state a moment ago under the new season's key;
    // the effect above fetches the right values for the new season first,
    // and *that* state update is what triggers this save (reading
    // `season`'s current value via closure, which has by then already
    // settled to the new season).
    if (!platformLoadedRef.current) return;
    savePlatformSettings({ season, platform, contest }).catch(() => {
      // Best-effort, same reasoning as the season/week save above.
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [platform, contest]);

  return (
    <div className="app">
      <header>
        <div>
          <h1>DFS</h1>
          <p className="app-version" title={`Built ${new Date(BUILD_TIME).toLocaleString()}`}>
            v{FRONTEND_VERSION} · built {new Date(BUILD_TIME).toLocaleString()}
          </p>
        </div>
        {/* Editing season/week/platform/contest now happens here, from
            any tab, instead of requiring a trip to Settings -- see
            HeaderSettingsPopover's own docstring. */}
        <HeaderSettingsPopover
          season={season}
          week={week}
          onSeasonChange={setSeason}
          onWeekChange={setWeek}
          platform={platform}
          contest={contest}
          onPlatformChange={setPlatform}
          onContestChange={setContest}
        />
      </header>

      {/* Ordered by the actual weekly workflow rather than build order:
          (1) Settings always first -- season/week/platform/contest config
          everything else reads. (2) Last week's own review, which informs
          this week's setup -- Contest Results (how your own lineups did),
          DK Players (the tracker those results/game logs read from), Game
          Logs/Game Logs Against/Multipliers (recent-history and pricing
          review). (3) This week's game-environment/usage inputs -- Compare
          Depth Charts, Vegas Lines, Usage Bump(+Players). (4) This week's
          pricing/ownership -- Salary Blocks, Ownership Summary/Pivots. (5)
          Building this week's pool -- Boom/Bust, Player Rankings, My Player
          Pool, the final step before setting a lineup. */}
      <div className="view-tabs">
        <button
          type="button"
          className={`view-tab${view === "settings" ? " selected" : ""}`}
          aria-pressed={view === "settings"}
          onClick={() => requestViewChange("settings")}
        >
          Settings
        </button>
        <button
          type="button"
          className={`view-tab${view === "contestResults" ? " selected" : ""}`}
          aria-pressed={view === "contestResults"}
          onClick={() => requestViewChange("contestResults")}
        >
          Contest Results
        </button>
        <button
          type="button"
          className={`view-tab${view === "dkPlayers" ? " selected" : ""}`}
          aria-pressed={view === "dkPlayers"}
          onClick={() => requestViewChange("dkPlayers")}
        >
          DK Players
        </button>
        <button
          type="button"
          className={`view-tab${view === "lineupScenarios" ? " selected" : ""}`}
          aria-pressed={view === "lineupScenarios"}
          onClick={() => requestViewChange("lineupScenarios")}
        >
          Lineup Scenarios
        </button>
        <button
          type="button"
          className={`view-tab${view === "gamePreview" ? " selected" : ""}`}
          aria-pressed={view === "gamePreview"}
          onClick={() => requestViewChange("gamePreview")}
        >
          Game Previews
        </button>
        <button
          type="button"
          className={`view-tab${view === "gameLogs" ? " selected" : ""}`}
          aria-pressed={view === "gameLogs"}
          onClick={() => requestViewChange("gameLogs")}
        >
          Game Logs
        </button>
        <button
          type="button"
          className={`view-tab${view === "gameLogsAgainst" ? " selected" : ""}`}
          aria-pressed={view === "gameLogsAgainst"}
          onClick={() => requestViewChange("gameLogsAgainst")}
        >
          Game Logs Against
        </button>
        <button
          type="button"
          className={`view-tab${view === "multipliers" ? " selected" : ""}`}
          aria-pressed={view === "multipliers"}
          onClick={() => requestViewChange("multipliers")}
        >
          Multipliers
        </button>
        <button
          type="button"
          className={`view-tab${view === "dstTrends" ? " selected" : ""}`}
          aria-pressed={view === "dstTrends"}
          onClick={() => requestViewChange("dstTrends")}
        >
          DST/Off Trends
        </button>
        <button
          type="button"
          className={`view-tab${view === "compare" ? " selected" : ""}`}
          aria-pressed={view === "compare"}
          onClick={() => requestViewChange("compare")}
        >
          Compare Depth Charts
        </button>
        <button
          type="button"
          className={`view-tab${view === "depthCharts" ? " selected" : ""}`}
          aria-pressed={view === "depthCharts"}
          onClick={() => requestViewChange("depthCharts")}
        >
          Depth Charts
        </button>
        <button
          type="button"
          className={`view-tab${view === "injuryReport" ? " selected" : ""}`}
          aria-pressed={view === "injuryReport"}
          onClick={() => requestViewChange("injuryReport")}
        >
          Injury Report
        </button>
        <button
          type="button"
          className={`view-tab${view === "vegasLines" ? " selected" : ""}`}
          aria-pressed={view === "vegasLines"}
          onClick={() => requestViewChange("vegasLines")}
        >
          Vegas Lines
        </button>
        <button
          type="button"
          className={`view-tab${view === "weather" ? " selected" : ""}`}
          aria-pressed={view === "weather"}
          onClick={() => requestViewChange("weather")}
        >
          Weather
        </button>
        <button
          type="button"
          className={`view-tab${view === "bump" ? " selected" : ""}`}
          aria-pressed={view === "bump"}
          onClick={() => requestViewChange("bump")}
        >
          Usage Bump
        </button>
        <button
          type="button"
          className={`view-tab${view === "usageBumpPlayers" ? " selected" : ""}`}
          aria-pressed={view === "usageBumpPlayers"}
          onClick={() => requestViewChange("usageBumpPlayers")}
        >
          Usage Bump Players
        </button>
        <button
          type="button"
          className={`view-tab${view === "salaryBlocks" ? " selected" : ""}`}
          aria-pressed={view === "salaryBlocks"}
          onClick={() => requestViewChange("salaryBlocks")}
        >
          Salary Blocks
        </button>
        <button
          type="button"
          className={`view-tab${view === "ownershipSummary" ? " selected" : ""}`}
          aria-pressed={view === "ownershipSummary"}
          onClick={() => requestViewChange("ownershipSummary")}
        >
          Ownership Summary
        </button>
        <button
          type="button"
          className={`view-tab${view === "ownership" ? " selected" : ""}`}
          aria-pressed={view === "ownership"}
          onClick={() => requestViewChange("ownership")}
        >
          Ownership Pivots
        </button>
        <button
          type="button"
          className={`view-tab${view === "boomBust" ? " selected" : ""}`}
          aria-pressed={view === "boomBust"}
          onClick={() => requestViewChange("boomBust")}
        >
          Boom/Bust Players
        </button>
        <button
          type="button"
          className={`view-tab${view === "playerPool" ? " selected" : ""}`}
          aria-pressed={view === "playerPool"}
          onClick={() => requestViewChange("playerPool")}
        >
          Player Rankings
        </button>
        <button
          type="button"
          className={`view-tab${view === "myPlayerPool" ? " selected" : ""}`}
          aria-pressed={view === "myPlayerPool"}
          onClick={() => requestViewChange("myPlayerPool")}
        >
          My Player Pool
        </button>
      </div>

      {view === "settings" && (
        <SettingsView season={season} week={week} platform={platform} contest={contest} />
      )}
      {view === "contestResults" && (
        <ContestResultsView season={season} week={week} platform={platform} contest={contest} />
      )}
      {view === "dkPlayers" && <DkPlayersView season={season} week={week} platform={platform} />}
      {view === "lineupScenarios" && (
        <LineupScenariosView season={season} week={week} platform={platform} contest={contest} />
      )}
      {view === "gamePreview" && (
        <GamePreviewView season={season} week={week} platform={platform} contest={contest} />
      )}
      {view === "gameLogs" && <GameLogsView season={season} week={week} platform={platform} contest={contest} />}
      {view === "gameLogsAgainst" && (
        <GameLogsAgainstView season={season} week={week} platform={platform} contest={contest} />
      )}
      {view === "multipliers" && (
        <MultipliersView season={season} week={week} platform={platform} contest={contest} />
      )}
      {view === "dstTrends" && <DstTrendsView season={season} week={week} />}
      {view === "compare" && (
        <CompareView refreshSignal={refreshSignal} onScraped={() => setRefreshSignal((n) => n + 1)} />
      )}
      {view === "depthCharts" && (
        <DepthChartsView refreshSignal={refreshSignal} onScraped={() => setRefreshSignal((n) => n + 1)} />
      )}
      {view === "injuryReport" && (
        <InjuryReportView season={season} week={week} contest={contest} refreshSignal={refreshSignal} />
      )}
      {view === "vegasLines" && <VegasLinesView season={season} week={week} />}
      {view === "weather" && <WeatherView season={season} week={week} />}
      {view === "bump" && (
        <UsageBumpView refreshSignal={refreshSignal} season={season} week={week} platform={platform} contest={contest} />
      )}
      {view === "usageBumpPlayers" && <UsageBumpPlayersView onDirtyChange={setUsageBumpPlayersDirty} />}
      {view === "salaryBlocks" && <SalaryBlocksView season={season} week={week} platform={platform} contest={contest} />}
      {view === "ownershipSummary" && (
        <OwnershipSummaryView season={season} week={week} platform={platform} contest={contest} />
      )}
      {view === "ownership" && <OwnershipView season={season} week={week} platform={platform} />}
      {view === "boomBust" && <BoomBustView season={season} week={week} platform={platform} contest={contest} />}
      {view === "playerPool" && <PlayerPoolView season={season} week={week} platform={platform} contest={contest} />}
      {view === "myPlayerPool" && (
        <MyPlayerPoolView season={season} week={week} platform={platform} contest={contest} />
      )}

      {pendingView !== null && (
        <ConfirmDialog
          message="You have unsaved changes on the Usage Bump Players tab. Switch tabs and discard them?"
          confirmLabel="Discard changes"
          onConfirm={() => {
            setView(pendingView);
            setPendingView(null);
          }}
          onCancel={() => setPendingView(null)}
        />
      )}
    </div>
  );
}

export default App;
