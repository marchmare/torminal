from google.transit.gtfs_realtime_pb2 import TripUpdate, Position, VehiclePosition
from datetime import datetime, timedelta, time, date
from dataclasses import dataclass
from typing import Any

from torminal.gtfs.realtime import PEKARealTimeFeed, fetch_gtfs_rt_feed, fetch_peka_vm_feed
from torminal.gtfs.utils import resolve_service_calendar, resolve_closest_stop
from torminal.gtfs.time import check_arrival_within_window, combine_today
from torminal.gtfs.data import (
    StopTime,
    Stop,
    Route,
    Vehicle,
    Trip,
    Position,
    BollardMessages,
    BollardMessage,
    ServiceCalendar,
    VehicleStatus,
)


class Query:
    """Class representing a single stop-line query added by user to monitor departures and wanted time window for upcoming arrivals."""

    def __init__(self, stop_code: str | int, route_id: str | int, time_window: int) -> None:
        self.stop_code = str(stop_code)
        self.route_id = str(route_id)
        self.time_window = time_window

    def __repr__(self) -> str:
        return f"stop ID: {self.stop_code}, route ID: {self.route_id}, time window: {self.time_window} min"


class ArrivalTime:
    """Class calculating planned and live arrival times"""

    time_: time
    """Exact time of arrival"""
    eta: int
    """Time left to arrival in minutes"""
    delay: int
    """Delay in seconds (can be negative, if vehicle passed a stop early)"""

    def __init__(self, arrival_time: time, delay: int = 0) -> None:

        self.time_ = arrival_time
        self.eta = self.estimate_arrival(arrival_time)
        self.delay = delay

    def __repr__(self) -> str:
        fields = (f"time={self.time_!r}", f"eta={self.eta!r}", f"delay={self.delay!r}")
        return f"{self.__class__.__name__}({', '.join(fields)})"

    @staticmethod
    def estimate_arrival(arrival_time: time) -> int:
        """Calculate how many minutes are left till vehicle departs."""
        delta = combine_today(arrival_time) - datetime.now()
        return int(delta.total_seconds() // 60)


@dataclass
class DepartureResult:
    planned_arrival: ArrivalTime
    realtime_arrival: ArrivalTime
    status: VehicleStatus = VehicleStatus.NO_RT
    message: BollardMessage | None = None
    position: Position | None = None
    current_stop: int | None = None


@dataclass
class QueryMatch:
    # data that can be assigned or derived at init and from static dataset
    trip: Trip
    stop_time: StopTime
    stop: Stop
    route: Route
    service: ServiceCalendar
    planned_arrival: time

    # below data can be obtained during first poll for RT data
    # data that is static during the entire trip but requires initial RT data access
    vehicle: Vehicle


class Monitor:
    """Monitor performing query polls."""

    def __init__(self, lookup) -> None:
        self._lookup = lookup

    def resolve_query(self, query: Query) -> list[QueryMatch]:
        """Find matching trips for the Query."""

        matches = []

        # determine stop and route data from lookup, resolve calendar
        stop = self._lookup.stops.get(query.stop_code, None)
        route = self._lookup.routes.get(query.route_id, None)
        service = resolve_service_calendar(self._lookup)

        for trip in self._lookup.trips.values():

            # filter out trips with not matching routes and not matching calendars
            if trip.route_id != route.id or trip.service_id != service.id:
                continue

            for stop_time in self._lookup.trip_stops[trip.id].items:
                # check if stop_time stop ID matches and if stop_time occurrs within queried time window
                if stop.id == stop_time.stop_id and check_arrival_within_window(
                    stop_time.arrival_time, time_window=query.time_window
                ):

                    matches.append(
                        QueryMatch(
                            trip=trip,
                            stop_time=stop_time,
                            stop=stop,
                            route=route,
                            service=service,
                            planned_arrival=stop_time.arrival_time,
                        )
                    )

        return matches

    def _get_realtime_feeds(
        self, query: QueryMatch
    ) -> tuple[TripUpdate | None, VehiclePosition | None, PEKARealTimeFeed]:
        gtfs_rt_feed = fetch_gtfs_rt_feed()
        peka_rt_feed = fetch_peka_vm_feed(query.stop)

        rt_trip_update = gtfs_rt_feed.trip_updates.get(query.trip.id, None)
        rt_vehicle_pos = gtfs_rt_feed.vehicle_positions.get(query.trip.id, None)
        rt_messages = peka_rt_feed.message

        return (rt_trip_update, rt_vehicle_pos, rt_messages)

    @staticmethod
    def is_vehicle_at_incoming(rt_vehicle_pos: VehiclePosition | None) -> bool:
        """
        Check if vehicle has `current_status` present and set to `AT_INCOMING`.
        This means the vehicle is at the terminus, waiting to begin a trip.
        """
        return rt_vehicle_pos.current_status == "AT_INCOMING" if hasattr(rt_vehicle_pos, "current_status") else False

    @staticmethod
    def calculate_rt_arrival_time(
        query: QueryMatch,
        stop_time_update: TripUpdate.StopTimeUpdate,
        status: VehicleStatus,
    ) -> ArrivalTime:
        """
        Calculate estimated arrival based on delay obtained from realtime feed.
        If vehicle is at terminus, planned arrival time will be used since it returns wrong delay in this case.
        """
        summed_delay_dt = combine_today(query.planned_arrival) + timedelta(seconds=stop_time_update.arrival.delay)
        _arrival_time = summed_delay_dt.time() if status is not VehicleStatus.AT_TERMINUS else query.planned_arrival
        return ArrivalTime(_arrival_time, stop_time_update.arrival.delay)

    def determine_status(
        self, query: QueryMatch, rt_vehicle_pos: VehiclePosition, rt_trip_update: TripUpdate
    ) -> VehicleStatus:
        """TODO"""
        return VehicleStatus.RUNNING

    def poll(self, query: QueryMatch) -> list[DepartureResult]:
        """Find upcoming arrivals for the query, that will occur within specified time window."""

        print(f"Polling {query.stop.id} {query.route.id}")

        # get realtime data about the found trip
        rt_trip_update, rt_vehicle_pos, rt_messages = self._get_realtime_feeds(query)

        stop_time_update = None
        message = None
        vehicle = None
        position = None
        planned_arrival = None
        realtime_arrival = None
        current_stop = None
        status = VehicleStatus.NO_RT

        planned_arrival = ArrivalTime(query.planned_arrival)

        if self.is_vehicle_at_incoming(rt_vehicle_pos):
            status = VehicleStatus.AT_TERMINUS
        else:
            status = VehicleStatus.RUNNING

        # get vehicle current position and stop sequence
        if rt_vehicle_pos:
            position = Position(rt_vehicle_pos.position.longitude, rt_vehicle_pos.position.latitude)
            current_stop = rt_vehicle_pos.current_stop_sequence
            query.position_history.append((rt_vehicle_pos.timestamp, current_stop, position))

        if rt_trip_update:
            if not query.vehicle:  # do not overwrite if already assigned
                query.vehicle = self._lookup.vehicles.get(rt_trip_update.vehicle.id, None)

            # calculate estimated live arrival time
            stop_time_update = resolve_closest_stop(query.stop_time.sequence, rt_trip_update.stop_time_update)
            realtime_arrival = self.calculate_rt_arrival_time(query, stop_time_update, status)

        self.determine_status(query, rt_vehicle_pos, rt_trip_update)

        _messages = BollardMessages.from_dict(rt_messages)
        message = _messages.get_current()

        return DepartureResult(
            message=message,
            position=position,
            planned_arrival=planned_arrival,
            realtime_arrival=realtime_arrival,
            current_stop=current_stop,
            status=status,
        )
