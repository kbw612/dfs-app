import { useState } from "react";
import "./App.css";
import { CompareView } from "./components/CompareView";
import { OwnershipView } from "./components/OwnershipView";
import { RetrieveButton } from "./components/RetrieveButton";
import { UsageBumpView } from "./components/UsageBumpView";
import { BUILD_TIME, FRONTEND_VERSION } from "./version";

type View = "compare" | "bump" | "ownership";

function App() {
  const [view, setView] = useState<View>("compare");
  // Bumped on every successful scrape so whichever view isn't currently
  // mounted still refetches next time it's shown, and the currently
  // mounted one refetches immediately.
  const [refreshSignal, setRefreshSignal] = useState(0);

  return (
    <div className="app">
      <header>
        <div>
          <h1>DFS</h1>
          <p className="app-version" title={`Built ${new Date(BUILD_TIME).toLocaleString()}`}>
            v{FRONTEND_VERSION} · built {new Date(BUILD_TIME).toLocaleString()}
          </p>
        </div>
        <RetrieveButton onScraped={() => setRefreshSignal((n) => n + 1)} />
      </header>

      <div className="view-tabs">
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
          Ownership Leverage/Pivots
        </button>
      </div>

      {view === "compare" && <CompareView refreshSignal={refreshSignal} />}
      {view === "bump" && <UsageBumpView refreshSignal={refreshSignal} />}
      {view === "ownership" && <OwnershipView />}
    </div>
  );
}

export default App;
