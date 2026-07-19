from google.transit.gtfs_realtime_pb2 import TripUpdate, VehiclePosition
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Self, Generator
from collections import defaultdict
from shapely.geometry import Point
import re

from torminal.config import config
from torminal.gtfs.gps import gps_point, calculate_mean_velocity
from torminal.gtfs.static import GTFSStaticFeed
from torminal.gtfs.realtime import PEKARealTimeFeed, GTFSRealTimeFeed
from torminal.gtfs.utils import resolve_service_calendar, ArrivalTime
from torminal.gtfs.data import (
    StopTime,
    Stop,
    Route,
    Vehicle,
    Trip,
    Shape,
    BollardMessages,
    BollardMessage,
    ServiceCalendar,
    VehicleStatus,
)


class Query:
    """Class representing a single stop-line query to get resolved."""

    def __init__(self, stop_code: str, route_id: str | int) -> None:
        self.stop_code = str(stop_code)
        self.route_id = str(route_id)

    def to_config(self) -> list[str, str]:
        """Convert to [stop_code, route_id] list, for use with config"""
        return [self.stop_code, self.route_id]

    @classmethod
    def from_input(cls, stop_input: str, route_intput: str) -> Self | None:
        """
        Return a Query based on user input. Following syntax of the input is assumed:

            * stop input: ' (CODE123) Stop Name  '
            * route input: '  123 Route direction - Route direction  ' (allows routes like T6)
        """
        re_stop_code = re.search(r"^\s*\(([^)]+)\)", stop_input)
        if not re_stop_code:
            return None
        stop_code = re_stop_code.group(1)

        re_route_id = re.search(r"^\s*([A-Za-z]?\d+)", route_intput)
        if not re_route_id:
            return None
        route_id = re_route_id.group(1)

        return cls(stop_code, route_id)


@dataclass
class QueryMatch:
    """Class representing a query that got resolved and got entities assigned from the GTFS dataset."""

    # data that can be assigned or derived at init and from static dataset
    trip: Trip
    stop_time: StopTime
    stop: Stop
    route: Route
    shape: Shape
    service: ServiceCalendar
    planned_arrival: datetime

    # below data can be obtained during first poll for RT data
    # data that is static during the entire trip but requires initial RT data access
    vehicle: Vehicle | None = None
    position_history: list[tuple[int, int | None, Point | None]] = field(default_factory=list)
    velocity_history: list[tuple[int, float | None]] = field(default_factory=list)

    def to_config(self) -> list[str, str]:
        """Convert to [stop_code, route_id] list, for use with config"""
        return [self.stop.code, self.route.id]


@dataclass
class RealtimePollResult:
    """Class representing data obtained from realtime feeds."""

    planned_arrival: ArrivalTime
    realtime_arrival: ArrivalTime | None
    status: VehicleStatus = VehicleStatus.NO_RT
    message: BollardMessage | None = None
    position: Point | None = None
    vehicle: str | None = None
    velocity: float | None = None
    current_stop: int | None = None


class Monitor:
    """Monitor performing query polls."""

    def __init__(self, datset: GTFSStaticFeed) -> None:
        self.dataset = datset
        self.time_window = config.time_window
        self.matched_queries: dict[str, list[QueryMatch]] = defaultdict(list)

    def add_query(self, query: Query) -> None:
        """Add query operation - adds query to config if it yields matches, returns resolved QueryMatches"""

        matches = self.resolve_query(query)
        if not matches:
            return

        config.add_query(query.to_config())

        for match in matches:
            self.matched_queries[match.stop.code].append(match)

    def remove_query(self, query: Query) -> None:
        """Remove query operation - removes query from config"""

        config.remove_query(query.to_config())

        if query.stop_code in self.matched_queries:

            self.matched_queries[query.stop_code] = [
                match for match in self.matched_queries[query.stop_code] if match.route.id != query.route_id
            ]

            if not self.matched_queries[query.stop_code]:
                del self.matched_queries[query.stop_code]

    def resolve_query(self, query: Query) -> list[QueryMatch]:
        """Find matching trips for the Query."""

        matches: list[QueryMatch] = []

        # determine stop and route data from lookup, resolve calendar
        stop = self.dataset.stops.get(query.stop_code, None)
        route = self.dataset.routes.get(query.route_id, None)
        service = resolve_service_calendar(self.dataset)

        if not stop or not route or not service:
            return matches

        for trip in self.dataset.trips.values():
            # filter out trips with not matching routes and not matching calendars
            if trip.route_id != route.id or trip.service_id != service.id:
                continue

            for stop_time in self.dataset.trip_stops[trip.id].items:
                # filter out stop times with not matching stops and outside time window

                if not stop.id == stop_time.stop_id or not self.check_arrival_within_window(stop_time.arrival_time):
                    continue
                shape = self.dataset.shapes.get(trip.shape_id, None)
                matches.append(
                    QueryMatch(
                        trip=trip,
                        stop_time=stop_time,
                        stop=stop,
                        route=route,
                        shape=shape,
                        service=service,
                        planned_arrival=stop_time.arrival_time,
                    )
                )
        return matches

    @staticmethod
    def resolve_closest_stop(
        sequence: int, stop_time_updates: list[TripUpdate.StopTimeUpdate]
    ) -> TripUpdate.StopTimeUpdate:
        """Out of Stop Time Update list entries, find the one that is closest to the queried stop sequence."""

        previous_stops = (update for update in stop_time_updates if update.stop_sequence < sequence)
        return max(previous_stops, key=lambda update: update.stop_sequence, default=None)

    def check_arrival_within_window(self, arrival_time: datetime) -> bool:
        """Calculate if arrival time for trip stop event will occur within Monitor's time window period counted from current time."""

        time_start = datetime.now()
        time_end = time_start + timedelta(minutes=config.time_window)
        return time_start < arrival_time < time_end

    def calculate_rt_arrival_time(self, query: QueryMatch, rt_trip_update: TripUpdate) -> ArrivalTime | None:
        """Calculate estimated arrival based on delay obtained from realtime feed."""

        stop_time_update = self.resolve_closest_stop(query.stop_time.sequence, rt_trip_update.stop_time_update)
        if not stop_time_update:
            return None

        summed_delay_dt = query.planned_arrival + timedelta(
            seconds=stop_time_update.arrival.delay if stop_time_update else 0
        )
        return ArrivalTime(summed_delay_dt, stop_time_update.arrival.delay)

    def determine_status(
        self,
        query: QueryMatch,
        rt_trip_update: TripUpdate,
        rt_vehicle_pos: VehiclePosition,
    ) -> VehicleStatus:
        """Determine vehicle status based on realtime feeds data."""

        def is_vehicle_incoming_at(rt_vehicle_pos: VehiclePosition | None) -> bool:
            """Check if vehicle has `current_status` present and set to `INCOMING_AT`, meaning the vehicle is at the terminus, waiting to begin a trip."""
            if not rt_vehicle_pos:
                return False
            return rt_vehicle_pos.current_status == 0

        def is_vehicle_stuck(query: QueryMatch) -> bool:
            """Check if vehicle's recent average velocity is near 0 for prolonged time."""

            v_threshold = 2.0  # km/h
            window = 3 * 60  # 3 minutes
            history_len = int(window / config.gtfs_rt_poll_interval)
            history_slice = [v for _, v in query.velocity_history[-history_len:] if v is not None]

            return len(history_slice) >= history_len and (sum(history_slice) / len(history_slice)) < v_threshold

        def is_vehicle_detoured(query: QueryMatch, rt_vehicle_pos: VehiclePosition) -> bool:
            """Check if vehicle is in 100m proximity from the trip shape."""
            position = gps_point(rt_vehicle_pos.position.longitude, rt_vehicle_pos.position.latitude)
            return not query.shape.path.contains(position)

        status = VehicleStatus.NO_RT
        delay = 0

        if rt_trip_update:
            stop_time_update = self.resolve_closest_stop(query.stop_time.sequence, rt_trip_update.stop_time_update)
            if not stop_time_update:
                return status
            delay = stop_time_update.arrival.delay

        if rt_vehicle_pos:
            if is_vehicle_incoming_at(rt_vehicle_pos) and rt_vehicle_pos.current_stop_sequence == 0:
                status = VehicleStatus.AT_TERMINUS  # TODO: find better way to determine this
            else:
                if delay < -60:
                    status = VehicleStatus.EARLY
                elif 60 < delay <= 3 * 60:
                    status = VehicleStatus.SLIGHTLY_DELAYED
                elif delay > 3 * 60:
                    status = VehicleStatus.DELAYED
                else:
                    status = VehicleStatus.ON_TIME

                if is_vehicle_detoured(query, rt_vehicle_pos):
                    status = VehicleStatus.DETOURED
                if is_vehicle_stuck(query) and not status == VehicleStatus.AT_TERMINUS:
                    status = VehicleStatus.STUCK

        return status

    def poll_all(
        self,
        rt_feed: GTFSRealTimeFeed,
        peka_feeds: dict[str, PEKARealTimeFeed | None],
    ) -> Generator[RealtimePollResult, None, None]:
        """Poll all matched queries and yield results."""

        for stop, stop_matches in self.matched_queries.items():
            rt_msg = peka_feeds.get(stop)

            for match in stop_matches:
                rt_tu = rt_feed.trip_updates.get(match.trip.id)
                rt_vp = rt_feed.vehicle_positions.get(match.trip.id)
                yield self.poll(match, rt_tu, rt_vp, rt_msg)

    def poll(
        self,
        query: QueryMatch,
        rt_trip_update: TripUpdate | None,
        rt_vehicle_pos: VehiclePosition | None,
        rt_messages: PEKARealTimeFeed | None,
    ) -> RealtimePollResult:
        """Find upcoming arrivals for the query, that will occur within specified time window."""

        print(f"Polling {query.stop.id} {query.route.id}")

        timestamp = int(datetime.timestamp(datetime.now()))
        history_entry = (timestamp, None, None)
        velocity_entry = (timestamp, None)
        velocity = None
        message = None
        position = None
        realtime_arrival = None
        current_stop = None
        planned_arrival = ArrivalTime(query.planned_arrival)

        # get data related to vehicle position GTFS-RT feed
        if rt_vehicle_pos:
            position = gps_point(rt_vehicle_pos.position.longitude, rt_vehicle_pos.position.latitude)
            current_stop = rt_vehicle_pos.current_stop_sequence
            history_entry = (timestamp, current_stop, position)
            velocity = calculate_mean_velocity(query.position_history[-5:])

            if velocity is not None:
                velocity_entry = (timestamp, velocity)

        # get data related to trip_update GTFS-RT feed
        if rt_trip_update:
            # get vehicle data
            if not query.vehicle:  # do not overwrite if already assigned
                query.vehicle = self.dataset.vehicles.get(rt_trip_update.vehicle.id, None)

            # calculate estimated live arrival time
            realtime_arrival = self.calculate_rt_arrival_time(query, rt_trip_update)

        # get data from PEKA virtual monitor
        if rt_messages:
            message = BollardMessages.from_dict(rt_messages.message).get_current()

        status = self.determine_status(query, rt_trip_update, rt_vehicle_pos)
        query.position_history.append(history_entry)
        query.velocity_history.append(velocity_entry)

        return RealtimePollResult(
            message=message,
            position=position,
            planned_arrival=planned_arrival,
            realtime_arrival=realtime_arrival,
            current_stop=current_stop,
            status=status,
            velocity=velocity,
            vehicle=query.vehicle.id if query.vehicle else None,
        )
