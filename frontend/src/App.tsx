import { useEffect, useRef, useState } from "react";
import "./App.css";
import { fetchCurrentWeek, fetchPlatformSettings, saveCurrentWeek, savePlatformSettings } from "./api";
import { CompareView } from "./components/CompareView";
import { OwnershipView } from "./components/OwnershipView";
import { PlayerPoolView } from "./components/PlayerPoolView";
import { RetrieveButton } from "./components/RetrieveButton";
import { SalaryBlocksView } from "./components/SalaryBlocksView";
import { SettingsView } from "./components/SettingsView";
import { UsageBumpView } from "./components/UsageBumpView";
import { BUILD_TIME, FRONTEND_VERSION } from "./version";

type View = "settings" | "compare" | "bump" | "ownership" | "salaryBlocks" | "playerPool";

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

  // The single (platform, contest) pointer shared by every tab that
  // touches a platform-specific file (currently just Player Pool's salary
  // read and the Settings tab's upload widgets) -- set via the Settings
  // tab's top panel, persisted server-side (see backend/api/
  // platform_settings) the same way season/week is. Only "DraftKings" /
  // "Classic Main" are real options today (see SettingsView.tsx).
  const [platform, setPlatform] = useState("DraftKings");
  const [contest, setContest] = useState("Classic Main");
  const platformLoadedRef = useRef(false);

  useEffect(() => {
    fetchCurrentWeek()
      .then((cw) => {
        setSeason(cw.season);
        setWeek(cw.week);
      })
      .finally(() => {
        weekLoadedRef.current = true;
      });
    fetchPlatformSettings()
      .then((ps) => {
        setPlatform(ps.platform);
        setContest(ps.contest);
      })
      .finally(() => {
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
    // Same echo-skip as season/week above. Chip selections are discrete
    // clicks, not continuous typing, so this saves immediately rather
    // than debouncing.
    if (!platformLoadedRef.current) return;
    savePlatformSettings({ platform, contest }).catch(() => {
      // Best-effort, same reasoning as the season/week save above.
    });
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
        {/* Editing season/week now happens on the Settings tab -- this is
            just an at-a-glance readout so the other tabs still show what
            week they're pointed at. */}
        <p className="current-week-readout">
          Season {season} · Week {week}
        </p>
        <RetrieveButton onScraped={() => setRefreshSignal((n) => n + 1)} />
      </header>

      <div className="view-tabs">
        <button
          type="button"
          className={`view-tab${view === "settings" ? " selected" : ""}`}
          aria-pressed={view === "settings"}
          onClick={() => setView("settings")}
        >
          Settings
        </button>
        <button
          type="button"
          className={`view-tab${view === "compare" ? " selected" : ""}`}
          aria-pressed={view === "compare"}
          onClick={() => setView("compare")}
        >
          Compare Depth Charts
        </button>
        <button
          type="button"
          className={`view-tab${view === "bump" ? " selected" : ""}`}
          aria-pressed={view === "bump"}
          onClick={() => setView("bump")}
        >
          Usage Bump Players
        </button>
        <button
          type="button"
          className={`view-tab${view === "ownership" ? " selected" : ""}`}
          aria-pressed={view === "ownership"}
          onClick={() => setView("ownership")}
        >
          Ownership Pivots
        </button>
        <button
          type="button"
          className={`view-tab${view === "salaryBlocks" ? " selected" : ""}`}
          aria-pressed={view === "salaryBlocks"}
          onClick={() => setView("salaryBlocks")}
        >
          Salary Blocks
        </button>
        <button
          type="button"
          className={`view-tab${view === "playerPool" ? " selected" : ""}`}
          aria-pressed={view === "playerPool"}
          onClick={() => setView("playerPool")}
        >
          Player Pool
        </button>
      </div>

      {view === "settings" && (
        <SettingsView
          season={season}
          week={week}
          onSeasonChange={setSeason}
          onWeekChange={setWeek}
          platform={platform}
          contest={contest}
          onPlatformChange={setPlatform}
          onContestChange={setContest}
        />
      )}
      {view === "compare" && <CompareView refreshSignal={refreshSignal} />}
      {view === "bump" && <UsageBumpView refreshSignal={refreshSignal} />}
      {view === "ownership" && <OwnershipView season={season} week={week} />}
      {view === "salaryBlocks" && <SalaryBlocksView season={season} week={week} platform={platform} />}
      {view === "playerPool" && <PlayerPoolView season={season} week={week} platform={platform} />}
    </div>
  );
}

export default App;
