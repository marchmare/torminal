from google.transit.gtfs_realtime_pb2 import TripUpdate
from torminal.gtfs.data import ServiceCalendar
from torminal.gtfs.static import GTFSStaticFeed
from datetime import datetime

weekday_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def resolve_closest_stop(
    sequence: int, stop_time_updates: list[TripUpdate.StopTimeUpdate]
) -> TripUpdate.StopTimeUpdate:
    """Out of Stop Time Update list entries, find the one that is closest to the queried stop sequence."""

    previous_stops = (update for update in stop_time_updates if update.stop_sequence < sequence)
    return max(previous_stops, key=lambda update: update.stop_sequence, default=None)


def resolve_service_calendar(lookup: GTFSStaticFeed) -> ServiceCalendar | None:
    """Get service calendar object for today's weekday."""

    current_weekday = datetime.today().weekday()

    for service in lookup.service_calendars.values():
        if getattr(service, weekday_names[current_weekday]):
            return service
    return None
