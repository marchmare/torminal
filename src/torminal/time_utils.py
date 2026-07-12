"""Datetime operations and converting to and from GTFS string formats."""

from datetime import datetime, date, timedelta


def convert_feed_info_date(date_str: str) -> datetime:
    """Convert feed info date string (YYYYMMDD e.g. 20260717) to date object."""

    return datetime.strptime(date_str, "%Y%m%d")


def convert_time_to_today(time_str: str) -> datetime:
    """Convert feed info time string (HH:MM:SS e.g. 20:34:00) to date object, combined with today's date."""

    return datetime.combine(date.today(), datetime.strptime(time_str, "%H:%M:%S").time())


def convert_time_to_gtfs(datetime: datetime) -> str:
    """Convert datetime object to time string in HH:MM:SS format."""

    return datetime.strftime("%H:%M:%S")


def check_arrival_within_window(arrival_time: str, time_window: int) -> bool:
    """Calculate if arrival time for trip stop event will occur within a time period specified by `minutes` argument, counted from current time."""

    time_start = datetime.now()
    time_end = time_start + timedelta(minutes=time_window)
    stop_time = convert_time_to_today(arrival_time)

    return time_start < stop_time < time_end
