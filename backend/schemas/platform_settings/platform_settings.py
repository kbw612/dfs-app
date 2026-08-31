"""
Platform Settings: the single (platform, contest) pair shared across every
tab that deals with a specific DFS site's export -- picked once in the
Settings tab's top panel (see frontend/src/components/SettingsView.tsx)
rather than each tab guessing which platform's file it should be looking
for. There is exactly one of these at a time, same "single current value,
not a history" shape as Current Week (backend/schemas/current_week/
current_week.py).

`platform` also determines the filename prefix used for this week's
shared salary/ownership files -- see
backend/services/platform_settings/prefix.py -- so a valid `platform`
value here must also be one prefix.py knows how to map. `contest` isn't
used by any file-naming or scoring logic yet (there's only ever been one
contest type, DraftKings Classic) -- it's stored/displayed for now so the
Settings panel has somewhere to hold it, ready for when contest-specific
behavior (Showdown roster rules, etc.) actually gets built.
"""

from __future__ import annotations

from pydantic import BaseModel


class PlatformSettings(BaseModel):
    platform: str
    contest: str
