import type { NameAlias } from "./types";

// Mirrors backend/services/dk_players/dk_players_engine.py's
// name_lookup_candidates() -- same reasoning applies here: two
// independently-maintained lists of player names (there, DK's stat file
// vs. the salary file; here, Settings' Player Default Factors grid vs.
// whatever this week's DK salary export spells a name as) can drift on
// suffixes (Jr./Sr./II/III) or other spelling quirks, and Name Aliases
// (Settings' Name Aliases panel, see NameAliasesPanel.tsx) is the single
// place a user records "these two strings are the same player."
//
// Given one name, returns every spelling that should be treated as the
// same player: the name itself, its alias-to-canonical mapping if it has
// one, and (the reverse direction) every alias that maps *to* this name if
// it's itself a canonical. Checking both directions means it doesn't
// matter which side of an alias pair the caller's name happens to be --
// e.g. a Player Default saved as "Brian Thomas" and a salary file spelling
// of "Brian Thomas Jr." both resolve to the same candidate set as long as
// one alias row connects them, regardless of which one is the "alias" and
// which is the "canonical" in that row.
export function nameLookupCandidates(name: string, aliases: NameAlias[]): string[] {
  const candidates = [name];
  const forward = aliases.find((a) => a.alias === name)?.canonical;
  if (forward !== undefined && !candidates.includes(forward)) {
    candidates.push(forward);
  }
  for (const { alias, canonical } of aliases) {
    if (canonical === name && !candidates.includes(alias)) {
      candidates.push(alias);
    }
  }
  return candidates;
}
