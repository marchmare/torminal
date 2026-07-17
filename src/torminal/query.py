from google.transit.gtfs_realtime_pb2 import TripUpdate, Position, VehiclePosition
from datetime import datetime, timedelta, time
from dataclasses import dataclass, field
from typing import Self
import re

from torminal.gtfs.static import GTFSStaticFeed
from torminal.gtfs.realtime import PEKARealTimeFeed
from torminal.gtfs.utils import resolve_service_calendar, ArrivalTime
from torminal.gtfs.time import combine_today
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
    """Class representing a single stop-line query to get resolved."""

    def __init__(self, stop_code: str, route_id: str | int, time_window: int) -> None:
        self.stop_code = str(stop_code)
        self.route_id = str(route_id)
        self.time_window = time_window

    @classmethod
    def from_input(cls, stop_input: str, route_intput: str) -> Self:
        """
        Return a Query based on user input. Following syntax of the input is assumed:

            * stop input: ' (CODE123) Stop Name  '
            * route input: '  123 Route direction - Route direction  ' (allows routes like T6)
        """

        stop_code = re.search(r"^\s*\(([^)]+)\)", stop_input).group(1)
        route_id = re.search(r"^\s*([A-Za-z]?\d+)", route_intput).group(1)
        return cls(stop_code, route_id)


@dataclass
class QueryMatch:
    """Class representing a query that got resolved and got entities assigned from the GTFS dataset."""

    # data that can be assigned or derived at init and from static dataset
    trip: Trip
    stop_time: StopTime
    stop: Stop
    route: Route
    service: ServiceCalendar
    planned_arrival: time

    # below data can be obtained during first poll for RT data
    # data that is static during the entire trip but requires initial RT data access
    vehicle: Vehicle | None = None
    position_history: list[tuple[int, int | None, Position | None]] = field(default_factory=list)


@dataclass
class RealtimePollResult:
    """Class representing data obtained from realtime feeds."""

    planned_arrival: ArrivalTime
    realtime_arrival: ArrivalTime
    status: VehicleStatus = VehicleStatus.NO_RT
    message: BollardMessage | None = None
    position: Position | None = None
    vehicle: int | None = None
    current_stop: int | None = None


class Monitor:
    """Monitor performing query polls."""

    def __init__(self, datset: GTFSStaticFeed, time_window: int = 30) -> None:
        self.dataset = datset
        self.time_window = time_window

    def resolve_query(self, query: Query) -> list[QueryMatch]:
        """Find matching trips for the Query."""

        matches = []

        # determine stop and route data from lookup, resolve calendar
        stop = self.dataset.stops.get(query.stop_code, None)
        route = self.dataset.routes.get(query.route_id, None)
        service = resolve_service_calendar(self.dataset)

        for trip in self.dataset.trips.values():

            # filter out trips with not matching routes and not matching calendars
            if trip.route_id != route.id or trip.service_id != service.id:
                continue

            for stop_time in self.dataset.trip_stops[trip.id].items:

                # filter out stop times with not matching stops and outside time window
                if not stop.id == stop_time.stop_id or not self.check_arrival_within_window(stop_time.arrival_time):
                    continue
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

    @staticmethod
    def resolve_closest_stop(
        sequence: int, stop_time_updates: list[TripUpdate.StopTimeUpdate]
    ) -> TripUpdate.StopTimeUpdate:
        """Out of Stop Time Update list entries, find the one that is closest to the queried stop sequence."""

        previous_stops = (update for update in stop_time_updates if update.stop_sequence < sequence)
        return max(previous_stops, key=lambda update: update.stop_sequence, default=None)

    def check_arrival_within_window(self, arrival_time: time) -> bool:
        """Calculate if arrival time for trip stop event will occur within Monitor's time window period counted from current time."""

        time_start = datetime.now()
        time_end = time_start + timedelta(minutes=self.time_window)
        return time_start < combine_today(arrival_time) < time_end

    def calculate_rt_arrival_time(self, query: QueryMatch, rt_trip_update: TripUpdate) -> ArrivalTime:
        """Calculate estimated arrival based on delay obtained from realtime feed."""

        stop_time_update = self.resolve_closest_stop(query.stop_time.sequence, rt_trip_update.stop_time_update)
        summed_delay_dt = combine_today(query.planned_arrival) + timedelta(
            seconds=stop_time_update.arrival.delay if stop_time_update else 0
        )
        time_ = summed_delay_dt.time()
        return ArrivalTime(time_, stop_time_update.arrival.delay)

    def determine_status(
        self,
        query: QueryMatch,
        rt_trip_update: TripUpdate,
        rt_vehicle_pos: VehiclePosition,
    ) -> VehicleStatus:
        """Determine vehicle status based on realtime feeds data."""

        def is_vehicle_incoming_at(rt_vehicle_pos: VehiclePosition | None) -> bool:
            """Check if vehicle has `current_status` present and set to `INCOMING_AT`, meaning the vehicle is at the terminus, waiting to begin a trip."""
            return rt_vehicle_pos.current_status == 0 if hasattr(rt_vehicle_pos, "current_status") else False

        status = VehicleStatus.NO_RT
        delay = 0

        if rt_trip_update:
            stop_time_update = self.resolve_closest_stop(query.stop_time.sequence, rt_trip_update.stop_time_update)
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

        # dependent on position history
        # TODO: determine DETOURED - check if last sequence change ocurred at position defined in Stop
        # TODO: determine STUCK - check if position of last n updates didn't change much

        return status

    def poll(
        self,
        query: QueryMatch,
        rt_trip_update: TripUpdate | None,
        rt_vehicle_pos: VehiclePosition | None,
        rt_messages: PEKARealTimeFeed,
    ) -> RealtimePollResult:
        """Find upcoming arrivals for the query, that will occur within specified time window."""

        print(f"Polling {query.stop.id} {query.route.id}")

        timestamp = datetime.timestamp(datetime.now())
        history_entry = (timestamp, None, None)
        message = None
        position = None
        realtime_arrival = None
        current_stop = None
        planned_arrival = ArrivalTime(query.planned_arrival)

        # get data related to vehicle position GTFS-RT feed
        if rt_vehicle_pos:
            position = Position(rt_vehicle_pos.position.longitude, rt_vehicle_pos.position.latitude)
            current_stop = rt_vehicle_pos.current_stop_sequence
            history_entry = (timestamp, current_stop, position)

        # get data related to trip_update GTFS-RT feed
        if rt_trip_update:
            # get vehicle data
            if not query.vehicle:  # do not overwrite if already assigned
                query.vehicle = self.dataset.vehicles.get(rt_trip_update.vehicle.id, None)

            # calculate estimated live arrival time
            realtime_arrival = self.calculate_rt_arrival_time(query, rt_trip_update)

        # get data from PEKA virtual monitor
        message = BollardMessages.from_dict(rt_messages.message).get_current()

        status = self.determine_status(query, rt_trip_update, rt_vehicle_pos)
        query.position_history.append(history_entry)

        return RealtimePollResult(
            message=message,
            position=position,
            planned_arrival=planned_arrival,
            realtime_arrival=realtime_arrival,
            current_stop=current_stop,
            status=status,
            vehicle=query.vehicle.id if query.vehicle else None,
        )
