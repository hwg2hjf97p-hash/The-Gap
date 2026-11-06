"""
Garmin numbers as the insights engine's daily table.

Unlike Whoop or Oura, nothing is fetched here: Garmin sends its numbers to us (routers/garmin.py) and they are kept in garmin_daily.
This reads those stored days back as the same standard daily columns the other connections produce.

It is only called when GARMIN_AI_ALLOWED is on (see utils/garmin.py): Garmin's licence does not allow Garmin data to feed an AI
system without Garmin's written agreement, so until that is switched on the engine and Gappy never see it.
"""

from __future__ import annotations

import logging

import pandas as pd

from utils import garmin

logger = logging.getLogger(__name__)

WINDOW_DAYS = 180  # the same lookback as the other connections


async def fetch_garmin_data(user_id: str) -> pd.DataFrame:
    from routers.garmin import recent_rows  # imported here so the sync module doesn't pull in the web routes at start-up

    rows = await recent_rows(user_id, WINDOW_DAYS)
    by_date = garmin.frame_rows(rows)
    if not by_date:
        return pd.DataFrame()
    df = pd.DataFrame.from_dict(by_date, orient="index")
    df.index = pd.to_datetime(df.index)
    df.index.name = "date"
    df = df.sort_index()
    logger.info("Garmin sync: %d days read", len(df))
    return df
