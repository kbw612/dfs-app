// Warning banner shown above the Game / Team filters when the selected
// contest has no DK salary file for the week yet. Without that file the
// slate can't be narrowed to the contest's own games, so every league game
// and player shows (see the contest_salary_file_missing flag the Game Logs,
// Game Logs Against and Game Logs Summary endpoints return).
interface ContestFileNoticeProps {
  missing: boolean;
  contest: string;
  week: number;
}

export function ContestFileNotice({ missing, contest, week }: ContestFileNoticeProps) {
  if (!missing) return null;
  return (
    <div className="contest-file-notice" role="status">
      <span className="contest-file-notice-icon" aria-hidden="true">
        ⚠
      </span>
      <span>
        No {contest} salary file for week {week} — showing all games.
      </span>
    </div>
  );
}
