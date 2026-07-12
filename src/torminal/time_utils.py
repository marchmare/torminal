from datetime import datetime


def convert_feed_info_date(date_str: str) -> datetime:
    """Convert feed info date string (YYYYMMDD e.g. 20260717) to date object."""

    return datetime.strptime(date_str, "%Y%m%d")
