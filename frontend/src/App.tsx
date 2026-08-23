import { useState } from "react";
import "./App.css";
import { CompareView } from "./components/CompareView";
import { RetrieveButton } from "./components/RetrieveButton";
import { UsageBumpView } from "./components/UsageBumpView";

type View = "compare" | "bump";

function App() {
  const [view, setView] = useState<View>("compare");
  // Bumped on every successful scrape so whichever view isn't currently
  // mounted still refetches next time it's shown, and the currently
  // mounted one refetches immediately.
  const [refreshSignal, setRefreshSignal] = useState(0);

  return (
    <div className="app">
      <header>
        <h1>DFS</h1>
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
      </div>

      {view === "compare" ? (
        <CompareView refreshSignal={refreshSignal} />
      ) : (
        <UsageBumpView refreshSignal={refreshSignal} />
      )}
    </div>
  );
}

export default App;
