"""
Small shared helper for repositories that do a "read the whole JSON file,
modify one key, write the whole file back" pattern (see e.g.
player_pool/entries_repo.py's save_entry). Two real bugs are possible with
a naive `path.write_text(json.dumps(data))` under concurrent requests --
this app's FastAPI endpoints run their (sync) handlers in a thread pool,
so two nearly-simultaneous saves for the same file are two real OS
threads racing each other, not a purely theoretical concern:

1. A lost update: thread A reads the file, thread B reads that same
   (still-old) file before A writes, both modify their own key, both
   write back -- B's write wins and silently discards A's change, even
   though neither write corrupted anything on its own.
2. File corruption: if two threads' `write_text` calls interleave at the
   OS level, the bytes actually on disk can end up as a splice of both
   writes -- neither a valid old version nor a valid new one. This is
   exactly what happened to data/nfl/2026/dk_player_factors_week1.json in
   practice once Game Matchup's team+position propagation started firing
   several PlayerPoolEntry saves for the same file back to back (see
   backend/repositories/player_pool/entries_repo.py's docstring and
   PlayerPoolView.tsx's teammateKeysSharingMatchup) -- the file ended up
   with one player's entry's closing brace immediately followed by
   another write's un-opened tail, and json.loads() raised
   "Extra data" on every subsequent read.

`locked_read_modify_write` fixes both: a per-path lock makes the whole
read-modify-write one atomic critical section (fixing #1), and
`atomic_write_json` writes to a temp file then os.replace()s it onto the
real path (atomic on POSIX) so the file on disk is always either the
complete old version or the complete new version, never a partial/spliced
mix (fixing #2) -- regardless of what serializes the read-modify-write.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Callable

_locks_guard = threading.Lock()
_locks: dict[str, threading.Lock] = {}


def _lock_for(path: Path) -> threading.Lock:
    """One lock per distinct file path -- saves to two different weeks'
    (or platforms'/players') files never block each other, only two
    saves genuinely targeting the exact same file do."""
    key = str(path)
    with _locks_guard:
        lock = _locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _locks[key] = lock
        return lock


def atomic_write_json(path: Path, data: dict) -> None:
    """Writes `data` as indented JSON to `path` such that a reader can
    never observe a partial/corrupted file, even under a crash or a
    concurrent write elsewhere -- writes to a sibling temp file first,
    then atomically replaces `path` with it (os.replace is atomic on the
    same filesystem, which the temp file always is since it's created in
    `path`'s own parent directory)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, indent=2))
        os.replace(tmp_name, path)
    except BaseException:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)
        raise


def locked_read_modify_write(path: Path, load: Callable[[], dict], modify: Callable[[dict], None]) -> None:
    """Runs `load()` to get the current contents, `modify(data)` to apply
    the caller's change in place, then atomically writes the result to
    `path` -- all under a lock scoped to `path`, so two concurrent callers
    targeting the SAME file are fully serialized rather than racing (see
    this module's docstring for why that matters)."""
    with _lock_for(path):
        data = load()
        modify(data)
        atomic_write_json(path, data)
