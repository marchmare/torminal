from google.transit.gtfs_realtime_pb2 import TripUpdate, Position
from datetime import datetime, timedelta
from dataclasses import dataclass
from .gtfs import GTFSLookup, resolve_service_calendar, load_rt_lookup

from .time_utils import check_arrival_within_window, convert_time_to_today, convert_time_to_gtfs
from .data import StopTime, Stop, Route, Vehicle, Trip


def resolve_closest_stop(
    sequence: int, stop_time_updates: list[TripUpdate.StopTimeUpdate]
) -> TripUpdate.StopTimeUpdate:
    """Out of Stop Time Update list entries, find the one that is closest to the queried stop sequence."""

    previous_stops = (update for update in stop_time_updates if update.stop_sequence < sequence)
    return max(previous_stops, key=lambda update: update.stop_sequence, default=None)


class Query:
    """Class representing a single stop-line query added by user to monitor departures and wanted time window for upcoming arrivals."""

    def __init__(self, stop_id: str | int, route_id: str | int, time_window: int) -> None:
        self.stop_id = str(stop_id)
        self.route_id = str(route_id)
        self.time_window = time_window

    def __repr__(self) -> str:
        return f"stop ID: {self.stop_id}, route ID: {self.route_id}, time window: {self.time_window} min"


class ArrivalTime:
    """Class calculating planned and live arrival times"""

    def __init__(self, stop_time: StopTime, stop_time_update: TripUpdate.StopTimeUpdate) -> None:
        self.planned = stop_time.arrival_time
        self.planned_eta = self.estimate_arrival(stop_time.arrival_time)

        arrival_live_time = self.add_delay(stop_time.arrival_time, stop_time_update.arrival.delay)
        self.live = arrival_live_time if stop_time_update.stop_sequence > 0 else None
        self.live_eta = self.estimate_arrival(arrival_live_time) if stop_time_update.stop_sequence > 0 else None

        self.delay = stop_time_update.arrival.delay

    def __repr__(self) -> str:
        fields = (
            f"planned={self.planned!r}",
            f"planned_eta={self.planned_eta!r}",
            f"live={self.live!r}",
            f"live_eta={self.live_eta!r}",
            f"delay={self.delay!r}",
        )
        return f"{self.__class__.__name__}({', '.join(fields)})"

    @staticmethod
    def estimate_arrival(arrival_time: str) -> int:
        """Calculate how many minutes are left till vehicle departs."""

        time_start = datetime.now()
        _arrival_time = convert_time_to_today(arrival_time)
        delta = _arrival_time - time_start
        return int(delta.total_seconds() // 60)

    @staticmethod
    def add_delay(arrival_time: str, delay: int) -> str:
        """Add GTFS-RT delay values (seconds integer) to the arrival time in GTFS static format (%H:%M:%S)."""

        _arrival_time = convert_time_to_today(arrival_time)
        return convert_time_to_gtfs(_arrival_time + timedelta(seconds=delay))


@dataclass
class DepartureResult:
    stop: Stop
    stop_time: StopTime
    route: Route
    trip: Trip
    vehicle: Vehicle | None
    current_stop_sequence: int
    arrival: ArrivalTime
    position: Position


class Monitor:
    """Monitor performing query polls."""

    def __init__(self, lookup: GTFSLookup) -> None:
        self._lookup = lookup

    def poll(self, query: Query) -> list[DepartureResult]:
        """Find upcoming arrivals for the query, that will occur within specified time window."""

        print(f"Polling {query}")

        stop = self._lookup["stops"].get(query.stop_id, None)
        route = self._lookup["routes"].get(query.route_id, None)
        results: list[DepartureResult] = []

        service = resolve_service_calendar(self._lookup)

        if not service or not route or not stop:
            return results

        gtfs_rt_lookup = load_rt_lookup()

        for trip in self._lookup["trips"].values():

            if trip.route_id != route.id:
                continue

            for stop_time in self._lookup["trip_stops"][trip.id].items:
                if (
                    trip.service_id == service.id
                    and stop.id == stop_time.stop_id
                    and check_arrival_within_window(stop_time.arrival_time, time_window=query.time_window)
                ):  # match service calendar, stop ID and arrival within specified time window to pinpoint a stop_time

                    # get realtime data about the found trip
                    rt_trip_update = gtfs_rt_lookup["trip_updates"].get(trip.id, None)
                    rt_vehicle_pos = gtfs_rt_lookup["vehicle_positions"].get(trip.id, None)
                    if not rt_trip_update:
                        continue

                    # get most recent stop time update (uses stop sequence)
                    stop_time_update = resolve_closest_stop(stop_time.sequence, rt_trip_update.stop_time_update)
                    if not stop_time_update:
                        continue

                    # calculate arrival times and get vehicle data
                    arrival_time = ArrivalTime(stop_time, stop_time_update)
                    vehicle = self._lookup["vehicles"].get(rt_trip_update.vehicle.id, None)

                    results.append(
                        DepartureResult(
                            stop,
                            stop_time,
                            route,
                            trip,
                            vehicle,
                            stop_time_update.stop_sequence,
                            arrival_time,
                            rt_vehicle_pos.position,
                        )
                    )
        return results
