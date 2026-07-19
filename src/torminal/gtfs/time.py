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
    if hours > 24 and now.time() < time(4, 0):  # TODO: this needs to be the hour of night/day trip boundary
        base = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        base = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return base + timedelta(hours=hours, minutes=minutes, seconds=seconds)
