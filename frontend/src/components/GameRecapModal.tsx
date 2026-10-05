// Shows one game's recap text, scraped verbatim from walterfootball.com --
// this app never summarizes or rewrites it (see backend/schemas/game_recap/
// game_recap.py's own docstring). Reuses the same modal-backdrop/
// modal-dialog/modal-header/modal-close classes ConfirmDialog.tsx already
// established, so this doesn't introduce a second modal visual language.
import type { GameRecapEntry } from "../types";

interface GameRecapModalProps {
  entry: GameRecapEntry;
  sourceUrl: string;
  onClose: () => void;
}

export function GameRecapModal({ entry, sourceUrl, onClose }: GameRecapModalProps) {
  // recap_text's own paragraphs are joined with blank lines by the scraper
  // (see game_recap_scraper.py's _collect_recap_text) -- split back out so
  // each renders as its own <p> rather than one run-on block, and each
  // "- " line (a preserved bullet, e.g. an EDITOR'S NOTE aside) renders as
  // its own line within that paragraph rather than losing its bullet.
  const paragraphs = entry.recap_text.split("\n\n").filter((p) => p.trim().length > 0);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-dialog game-recap-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <span>
            {entry.away_team} {entry.away_team_score} @ {entry.home_team} {entry.home_team_score}
          </span>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        <div className="game-recap-modal-body">
          {paragraphs.length === 0 && <p className="hint">No recap text was captured for this game.</p>}
          {paragraphs.map((p, i) => (
            <p key={i} className="game-recap-paragraph">
              {p.split("\n").map((line, j) => (
                <span key={j}>
                  {line}
                  {j < p.split("\n").length - 1 && <br />}
                </span>
              ))}
            </p>
          ))}
        </div>
        <div className="game-recap-modal-source">
          Source:{" "}
          <a href={sourceUrl} target="_blank" rel="noopener noreferrer">
            WalterFootball.com
          </a>
        </div>
      </div>
    </div>
  );
}
