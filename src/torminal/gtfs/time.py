"""
Datetime operations and converting to and from GTFS string formats.

Time formats across TORminal:

* GTFS realtime:
    * vehicle position timestamp: 1784221676
    * PEKA virtual monitor bollard data: 2026-07-20T23:00:00.000Z (todays data and a time)
* GTFS static:
    * feed_info, calendar date: 20260717
    * stop_times time: 20:34:00
"""

from datetime import datetime, date, time, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd

weekday_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
fake_today = datetime(2026, 7, 17, 20, 0, 0)


def timestamp_to_dt(timestamp: int) -> datetime:
    """
    Convert Unix timestamp to datetime object (seconds since 1970-01-01 00:00:00 UTC).
    In GTFS-RT terms its `uint64 timestamp`.
    """

    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


def iso_to_dt(date: str) -> datetime:
    """Convert ISO 8601 datetime in UTC timezone to datetime object (e.g. 2026-07-20T23:00:00.000Z)"""

    return datetime.fromisoformat(date.replace("Z", "+00:00"))


def gtfs_date_to_dt(date: str) -> date:
    """Convert GTFS date string (YYYYMMDD e.g. 20260717) to datetime object"""

    return datetime.strptime(date, "%Y%m%d").date()


def gtfs_time_to_dt(gtfs_time: str) -> datetime:
    """
    Convert GTFS time string (HH:MM:SS e.g. 20:34:00) to datetime object.
    Handles times overflowing midnight (e.g. 25:03:00 -> tomorrow 01:03:00).
    """
    time_ = gtfs_time.split(":")
    hours, minutes, seconds = int(time_[0]), int(time_[1]), int(time_[2])
    now = datetime.now()
    return _time_base(now, hours) + timedelta(hours=hours, minutes=minutes, seconds=seconds)


def gtfs_dates_to_dt(gtfs_dates: pd.Series) -> list[date]:
    """Vectorized version of gtfs_date_to_dt for arrays of YYYYMMDD strings."""

    x = gtfs_dates.astype(int)
    iso = (
        (x // 10000).astype(str)
        + "-"
        + (x // 100 % 100).astype(str).str.zfill(2)
        + "-"
        + (x % 100).astype(str).str.zfill(2)
    )
    return pd.to_datetime(iso).dt.date.tolist()


def gtfs_times_to_dt(gtfs_times: pd.Series) -> list[datetime]:
    """
    Vectorized version of gtfs_time_to_dt for arrays of HH:MM:SS strings.
    Handles times overflowing midnight (e.g. 25:03:00 -> tomorrow 01:03:00).
    Assumes every value is exactly 8 characters long (zero-padded hours).
    """
    bytes_ = gtfs_times.to_numpy(dtype="S8").view(np.uint8).reshape(-1, 8)

    hours = (bytes_[:, 0] - 48) * 10 + (bytes_[:, 1] - 48)
    minutes = (bytes_[:, 3] - 48) * 10 + (bytes_[:, 4] - 48)
    seconds = (bytes_[:, 6] - 48) * 10 + (bytes_[:, 7] - 48)

    day_seconds = hours.astype(np.int64) * 3600 + minutes.astype(np.int64) * 60 + seconds.astype(np.int64)
    day_seconds_int = 24 * 60 * 60

    now = datetime.now()
    base = np.datetime64(now.replace(hour=0, minute=0, second=0, microsecond=0)).astype("datetime64[s]")
    base_shifted = base - np.where(_before_new_service_day(now, hours), day_seconds_int, 0).astype("timedelta64[s]")

    return (base_shifted + day_seconds.astype("timedelta64[s]")).tolist()


def _before_new_service_day(now: datetime, hours: Any) -> Any:
    """
    Check if time is post-midnight GTFS trip (hours > 24) that belong to the previous service day.
    Assumes set public transport provider service day begin time.
    """
    service_day_begin_time = 4
    return (hours > 24) & (now.time() < time(service_day_begin_time, 0))


def _time_base(now: datetime, hours: int) -> datetime:
    """Midnight base date for GTFS times, shifting a day back for post-midnight trips before new service day boundary."""
    if _before_new_service_day(now, hours):
        return (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)
