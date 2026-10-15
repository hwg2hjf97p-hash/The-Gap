"""
Keeps a confirmed insight from flickering.

The engine re-tests everything from scratch on every sync. A pattern sitting near the line
between "confirmed" and "early signal" can fall over it with a single new day of data, and back
again the next sync: someone sees a second insight in the morning and it is gone by the evening.
That is a statistical wobble, not the pattern vanishing, but on screen it looks like the app
losing its mind.

So a confirmed insight is remembered: if the next run no longer confirms it, the earlier version
stays for GRACE_DAYS since it was last confirmed (it is marked "carried"). If it is confirmed again
in that time, nothing ever visibly changed. If not, it quietly gives way to whatever the engine
now says. Each insight also records when it was first and last confirmed.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

GRACE_DAYS = 7
_ORDER = {"strong": 0, "moderate": 1, "weak": 2}


def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def is_confirmed(insight: dict) -> bool:
    return insight.get("confidence") not in (None, "weak")


def stabilise(previous: Optional[list[dict]], previous_saved_at: Optional[str], current: list[dict], now: Optional[datetime] = None) -> list[dict]:
    """The insights to show and save: this run's, with recently confirmed ones from the last run held on to."""
    now = now or datetime.now(timezone.utc)
    stamp = now.isoformat()
    saved_at = _parse(previous_saved_at)
    prev_by_id = {str(i["hypothesis_id"]): i for i in (previous or []) if i.get("hypothesis_id")}

    out: dict[str, dict] = {}
    for insight in current:
        hid = str(insight.get("hypothesis_id") or "")
        if not hid:
            continue
        item = dict(insight)
        if is_confirmed(item):
            before = prev_by_id.get(hid)
            first = (before or {}).get("first_confirmed_at") if before and is_confirmed(before) else None
            item["first_confirmed_at"] = first or (previous_saved_at if before and is_confirmed(before) else None) or stamp
            item["last_confirmed_at"] = stamp
            item["carried"] = False
        out[hid] = item

    for hid, before in prev_by_id.items():
        if not is_confirmed(before):
            continue
        now_item = out.get(hid)
        if now_item is not None and is_confirmed(now_item):
            continue
        last = _parse(before.get("last_confirmed_at")) or saved_at or now
        if now - last < timedelta(days=GRACE_DAYS):
            held = dict(before)
            held["carried"] = True
            held["last_confirmed_at"] = last.isoformat()
            held.setdefault("first_confirmed_at", last.isoformat())
            out[hid] = held

    return sorted(out.values(), key=lambda i: _ORDER.get(str(i.get("confidence")), 3))
