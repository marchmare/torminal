from torminal.data import ServiceCalendar
from google.transit import gtfs_realtime_pb2
from google.transit.gtfs_realtime_pb2 import TripUpdate
from .gtfs_static import GTFSLookup
from .data import Stop, ServiceCalendar
from datetime import timedelta, datetime, date
import requests

weekday_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

GTFS_RT_URL = "https://www.ztm.poznan.pl/pl/dla-deweloperow/getGtfsRtFile?file="


def get_gtfs_rt_data() -> dict[str, dict]:
    feeds_url = GTFS_RT_URL + "feeds.pb"  # aggregated data, not need
    trip_updates_url = GTFS_RT_URL + "trip_updates.pb"
    vehicle_positions_url = GTFS_RT_URL + "vehicle_positions.pb"  # not needed

    feed = gtfs_realtime_pb2.FeedMessage()
    response = requests.get(trip_updates_url)
    response.raise_for_status()

    feed.ParseFromString(response.content)

    return {e.trip_update.trip.trip_id: e.trip_update for e in feed.entity}


class Query:
    """Class representing a single stop-line query added by user to monitor departures."""

    def __init__(self, stop_code: str, route_id: str, lookup: GTFSLookup) -> None:
        feed = gtfs_realtime_pb2.FeedMessage()

        self._lookup = lookup
        self.stop = self.resolve_stop(stop_code)
        self.route = self._lookup["routes"].get(route_id, None)

    def resolve_stop(self, stop_code: str) -> Stop | None:
        """
        Get stop object by stop code.
        TODO: after TUI is implemented, this can be inline in __init__, similar to routes, since the stop ID will be picked
        """

        for stop in self._lookup["stops"].values():
            if stop.code == stop_code:
                return stop

    def resolve_service_calendar(self) -> ServiceCalendar | None:
        """Get service calendar object for today's weekday."""

        current_weekday = datetime.today().weekday()

        for service in self._lookup["service_calendars"].values():
            if getattr(service, weekday_names[current_weekday]):
                return service

    def check_arrival_within_window(self, arrival_time: str, time_window: int) -> bool:
        """Calculate if arrival time for trip stop event will occur within a time period specified by `minutes` argument, counted from current time."""

        time_start = datetime.now()
        # time_start = datetime.combine(date.today(), datetime.strptime("13:30:00", "%H:%M:%S").time())
        time_end = time_start + timedelta(minutes=time_window)
        stop_time = datetime.combine(date.today(), datetime.strptime(arrival_time, "%H:%M:%S").time())

        return time_start < stop_time < time_end

    def estimate_arrival(self, arrival_time: str) -> int:
        """Calculate how many minutes are left till vehicle departs."""

        time_start = datetime.now()
        # time_start = datetime.combine(date.today(), datetime.strptime("13:30:00", "%H:%M:%S").time())
        _arrival_time = datetime.combine(date.today(), datetime.strptime(arrival_time, "%H:%M:%S").time())

        delta = _arrival_time - time_start
        return int(delta.total_seconds() // 60)

    def add_delay(self, arrival_time: str, delay: int) -> int:
        """Add GTFS-RT delay values (seconds integer) to the arrival time in GTFS static format (%H:%M:%S)."""

        _arrival_time = datetime.combine(date.today(), datetime.strptime(arrival_time, "%H:%M:%S").time())
        return (_arrival_time + timedelta(seconds=delay)).strftime("%H:%M:%S")

    def resolve_closest_stop(
        self, sequence: int, stop_time_updates: list[TripUpdate.StopTimeUpdate]
    ) -> TripUpdate.StopTimeUpdate | None:
        """Out of Stop Time Update list entries, find the one that is closest to the queried stop sequence."""

        previous_stops = (update for update in stop_time_updates if update.stop_sequence < sequence)
        return max(previous_stops, key=lambda update: update.stop_sequence, default=None)

    def poll(self, time_window: int) -> None:
        """Find upcoming arrivals for the query, that will occur within specified time window."""

        print("Polling...")
        results = []
        service = self.resolve_service_calendar()
        gtfs_rt_data = get_gtfs_rt_data()
        for trip in self._lookup["trips"].values():

            if trip.route_id != self.route.id:
                continue

            for stop_time in self._lookup["trip_stops"][trip.id].items:
                if (
                    trip.service_id == service.id
                    and self.stop.id == stop_time.stop_id
                    and self.check_arrival_within_window(stop_time.arrival_time, time_window=time_window)
                ):

                    trip_update = gtfs_rt_data.get(trip.id, None)
                    if not trip_update:
                        continue

                    stop_time_update = self.resolve_closest_stop(stop_time.sequence, trip_update.stop_time_update)
                    if not stop_time_update:
                        continue

                    arrival_live_time = self.add_delay(stop_time.arrival_time, stop_time_update.arrival.delay)
                    vehicle = self._lookup["vehicles"].get(trip_update.vehicle.id, None)

                    results.append(
                        {
                            "_trip": trip,
                            "_stop_time": stop_time,
                            "_stop": self.stop,
                            "_route": self.route,
                            "_vehicle": vehicle,
                            "stop_sequence": stop_time.sequence,
                            "current_stop_sequence": stop_time_update.stop_sequence,
                            "trip_id": trip.id,
                            "vehicle_id": vehicle.id,
                            "route_id": self.route.id,
                            "stop_code": self.stop.code,
                            "stop_name": self.stop.name,
                            "arrival_planned_time": stop_time.arrival_time,
                            "arrival_planned_estimated": self.estimate_arrival(stop_time.arrival_time),
                            "arrival_live_time": arrival_live_time if stop_time_update.stop_sequence > 0 else None,
                            "arrival_live_estimated": (
                                self.estimate_arrival(arrival_live_time) if stop_time_update.stop_sequence > 0 else None
                            ),
                            "delay": stop_time_update.arrival.delay,
                        }
                    )
        return results
