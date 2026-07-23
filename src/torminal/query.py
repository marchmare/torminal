from google.transit.gtfs_realtime_pb2 import TripUpdate, VehiclePosition
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Self, Generator
from collections import defaultdict, deque
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


class QueryKey:
    """Class representing a single stop-line query to get resolved."""

    def __init__(self, stop_code: str, route_id: str | int) -> None:
        self.stop_code = str(stop_code)
        self.route_id = str(route_id)

    def to_config(self) -> list[str, str]:
        """Convert to [stop_code, route_id] list, for use with config"""
        return [self.stop_code, self.route_id]

    @classmethod
    def from_config(cls, query: list[str, str]) -> Self:
        """Return a Query based on list parsed from config"""
        return cls(*query)

    @classmethod
    def from_input(cls, stop_input: str, route_input: str) -> Self | None:
        """
        Return a Query based on user input. Following syntax of the input is assumed:

            * stop input: ' (CODE123) Stop Name  '
            * route input: '  (123) Route direction - Route direction  ' (allows routes like T6)
        """
        pattern = r"^\s*\(\s*([A-Z0-9]+)\s*\)"

        re_stop_code = re.search(pattern, stop_input)
        if not re_stop_code:
            return None
        stop_code = re_stop_code.group(1)

        re_route_id = re.search(pattern, route_input)
        if not re_route_id:
            return None
        route_id = re_route_id.group(1)

        return cls(stop_code, route_id)


@dataclass
class QueryMatch:
    """Class representing mutable query data."""

    trip: Trip  # stores Trip, Stop Times, Shape, Route, Service calendar
    stop_time: StopTime  # stores Stop, arrival time
    vehicle: Vehicle | None = None
    position_history: deque = field(default_factory=lambda: deque(maxlen=5))
    velocity_history: list[tuple[int, float]] = field(default_factory=list)


@dataclass
class RealtimePollResult:
    """Class representing data obtained from realtime feeds."""

    route_id: str
    destination: str
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
        self.queries: dict[Stop | str, dict[Route | str, list[QueryMatch]]] = {}

    def add_query(self, query: QueryKey) -> None:
        """Add query to config and to queries mapping."""

        # maintain queries mapping
        self.resolve_query(query)

        # maintain config
        config.add_query(query.to_config())

    def remove_query(self, query: QueryKey) -> None:
        """Remove query operation - removes query from config"""

        # maintain queries mapping
        if stop_queries := self.queries.get(query.stop_code):
            stop_queries.pop(query.route_id, None)

            if not stop_queries:
                del self.queries[query.stop_code]

        # maintain config
        config.remove_query(query.to_config())

    def resolve_query(self, query: QueryKey) -> bool:
        """
        Find matching trips for the Query and appends it to self.queries mapping.
        Returns True if new query is added successfully.
        This method populates queries dictionary with all possible trip and stop time matches
        that can occur for given stop and route combination.
        """

        stop_queries = self.queries.setdefault(query.stop_code, {})
        matches = stop_queries.setdefault(query.route_id, [])

        dataset = self.dataset.stop_route_index.get(query.stop_code, {}).get(query.route_id, [])
        matches.extend(QueryMatch(trip, stop_time) for trip, stop_time in dataset)

        return bool(matches)

    def validate_stop_exists(self, stop_code: str) -> bool:
        """Validate if Stop exists in current GTFS static dataset"""
        return stop_code in self.dataset.stops

    def validate_stop_on_route(self, stop_code: str, route_id: str) -> bool:
        """Validate if Stop belongs to a Route"""
        return route_id in self.dataset.stop_route_index.get(stop_code, {})

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

        summed_delay_dt = query.stop_time.arrival_time + timedelta(
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
            if shape := self.dataset.shapes.get(query.trip.shape_id):
                return not shape.path.contains(position)
            return False

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
    ) -> Generator[tuple[str, RealtimePollResult], None, None]:
        """Poll all matched queries and yield results."""

        service = resolve_service_calendar(self.dataset)

        for stop_code, routes in self.queries.items():
            rt_msg = peka_feeds.get(stop_code)

            for route_id, query_matches in routes.items():
                for match in query_matches:
                    if match.trip.service_id != service.id:
                        continue  # skip trips not matching service calendar

                    if not self.check_arrival_within_window(match.stop_time.arrival_time):
                        continue  # skip stop times outside configured time window

                    rt_tu = rt_feed.trip_updates.get(match.trip.id)
                    rt_vp = rt_feed.vehicle_positions.get(match.trip.id)

                    yield (stop_code, self.poll(match, rt_tu, rt_vp, rt_msg))

    def poll(
        self,
        query: QueryMatch,
        rt_trip_update: TripUpdate | None,
        rt_vehicle_pos: VehiclePosition | None,
        rt_messages: PEKARealTimeFeed | None,
    ) -> RealtimePollResult:
        """Find upcoming arrivals for the query, that will occur within specified time window."""

        print(f"Polling {query.stop.code} {query.route.id}")

        timestamp = int(datetime.timestamp(datetime.now()))
        history_entry = (timestamp, None, None)
        velocity_entry = (timestamp, None)
        velocity = None
        message = None
        position = None
        realtime_arrival = None
        current_stop = None
        planned_arrival = ArrivalTime(query.stop_time.arrival_time)

        # get data related to vehicle position GTFS-RT feed
        if rt_vehicle_pos:
            position = gps_point(rt_vehicle_pos.position.longitude, rt_vehicle_pos.position.latitude)
            current_stop = rt_vehicle_pos.current_stop_sequence
            history_entry = (timestamp, current_stop, position)
            velocity = calculate_mean_velocity(query.position_history)

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

        # update persisiting QueryMatch data
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
            route_id=query.route.id,
            destination=query.trip.headsign,
        )
