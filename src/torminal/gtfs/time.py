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

from datetime import datetime, date, time, timedelta

weekday_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
fake_today = datetime(2026, 7, 17, 20, 0, 0)


def timestamp_to_dt(timestamp: int) -> datetime:
    """
    Convert Unix timestamp to datetime object (seconds since 1970-01-01 00:00:00 UTC).
    In GTFS-RT terms its `uint64 timestamp`.
    """

    return datetime.fromtimestamp(timestamp, tz="UTC")


def iso_to_dt(date: str) -> datetime:
    """Convert ISO 8601 datetime in UTC timezone to datetime object (e.g. 2026-07-20T23:00:00.000Z)"""

    return datetime.fromisoformat(date.replace("Z", "+00:00"))


def gtfs_date_to_dt(date: str) -> date:
    """Convert GTFS date string (YYYYMMDD e.g. 20260717) to datetime object"""

    return datetime.strptime(date, "%Y%m%d").date()


def gtfs_time_to_dt(time: str) -> time:
    """
    Convert GTFS date string (HH:MM:SS e.g. 20:34:00) to datetime object.
    Time string is normalized in case it overlaps onto the next day (e.g. 25:01:00 -> 01:01:00).

    Important: the normalization most likely will introduce bugs, especially when calculating
    deltas around midnight.
    """

    _time = time.split(":")
    hours = int(_time[0])
    if hours > 23:
        hours = f"{hours - 24:02d}"
    _new_time = f"{hours}:{_time[1]}:{_time[2]}"

    return datetime.strptime(_new_time, "%H:%M:%S").time()


def combine_today(time: time) -> datetime:
    """Combine time object with today datetime."""
    return datetime.combine(date.today(), time)
