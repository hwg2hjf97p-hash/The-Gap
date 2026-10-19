"""
Fewer calls to a service's API on each refresh.

Whoop (and Oura, Strava) return a few records per call, so reading a person's last 180 days takes about 25 calls, and The
Gap used to do that every refresh (hourly, plus whenever the app was opened). With a daily call limit per app that adds
up fast: at that rate 10,000 calls a day covers only about 15 people.

Now the full 180 days is read once a day at most. In between, a refresh reads only the last couple of weeks (3 calls) and
puts those days over the saved copy, because older days don't change. The saved copy is held in the server's memory only
(never written to disk), is used only for that person, and is dropped after FULL_REFRESH_SECONDS.
"""

from __future__ import annotations

import time
from typing import Awaitable, Callable, Optional

import pandas as pd

FULL_DAYS = 180
RECENT_DAYS = 14
REPLACE_FROM_DAYS = 10  # days newer than this are taken from the fresh read; the margin keeps a half-read boundary day out
FULL_REFRESH_SECONDS = 24 * 3600

# (user, provider) -> (when the full read was done, the data)
_saved: dict[tuple[str, str], tuple[float, pd.DataFrame]] = {}

FetchFn = Callable[[str, int], Awaitable[Optional[pd.DataFrame]]]


def overlay_recent(old: pd.DataFrame, fresh: pd.DataFrame, today: pd.Timestamp, replace_days: int = REPLACE_FROM_DAYS) -> pd.DataFrame:
    """The saved days before the cut-off, plus every fresh day (which replaces whatever was saved for those days)."""
    cutoff = today.normalize() - pd.Timedelta(days=replace_days)
    kept = old[old.index < cutoff] if old is not None and not old.empty else old
    if fresh is None or fresh.empty:
        return old if old is not None else pd.DataFrame()
    fresh = fresh[fresh.index >= cutoff]
    combined = pd.concat([kept, fresh]) if kept is not None and not kept.empty else fresh
    combined = combined[~combined.index.duplicated(keep="last")].sort_index()
    combined.index.name = "date"
    return combined


def forget(user_id: str, provider: str) -> None:
    _saved.pop((user_id, provider), None)


def _drop_expired(now: float) -> None:
    for key in [k for k, (at, _) in _saved.items() if now - at >= FULL_REFRESH_SECONDS]:
        _saved.pop(key, None)


async def fetch_recent_first(user_id: str, provider: str, access_token: str, fetch: FetchFn, now: Optional[float] = None) -> Optional[pd.DataFrame]:
    """
    The person's data for the last FULL_DAYS days, reading all of it at most once a day and only the last RECENT_DAYS days
    otherwise. `fetch(access_token, days_back)` is the provider's own reader.
    """
    now = time.time() if now is None else now
    _drop_expired(now)
    key = (user_id, provider)
    saved = _saved.get(key)
    if saved is not None and saved[1] is not None and not saved[1].empty:
        fresh = await fetch(access_token, RECENT_DAYS)
        if fresh is not None and not fresh.empty:
            merged = overlay_recent(saved[1], fresh, pd.Timestamp.now(tz="UTC").tz_localize(None))
            _saved[key] = (saved[0], merged)  # keep the time of the last FULL read, so the daily full read still happens
            return merged
        return saved[1]  # the recent read found nothing new (or failed): the saved copy still stands
    full = await fetch(access_token, FULL_DAYS)
    if full is not None and not full.empty:
        _saved[key] = (now, full)
    return full
