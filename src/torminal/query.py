from torminal.data import ServiceCalendar

from .parser import GTFSLookup
from .data import Stop, Route, ServiceCalendar
from datetime import timedelta, datetime, date

weekday_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


class Query:
    """Class representing a single stop-line query added by user to monitor departures."""

    def __init__(self, stop_code: str, route_id: str, lookup: GTFSLookup) -> None:
        self._lookup = lookup
        self.stop = self.resolve_stop(stop_code)
        self.route = self.resolve_route(route_id)
        # self.destination = self.resolve_destination()

    def resolve_stop(self, stop_code: str) -> Stop | None:
        """Get stop object by stop code."""

        for stop in self._lookup["stops"].values():
            if stop.code == stop_code:
                return stop

    def resolve_route(self, route_id: str) -> Route | None:
        """Get route object by route ID."""

        return self._lookup["routes"].get(route_id, None)

    def resolve_service_calendar(self) -> ServiceCalendar | None:
        """Get service calendar object for today's weekday."""

        current_weekday = datetime.today().weekday()

        for service in self._lookup["service_calendars"].values():
            if getattr(service, weekday_names[current_weekday]):
                return service

    def check_arrival_within_window(self, arrival_time: str, minutes: int) -> bool:
        """Calculate if arrival time for trip stop event will occur within a time period specified by `minutes` argument, counted from current time."""

        # time_start = datetime.now()
        time_start = datetime.combine(date.today(), datetime.strptime("13:30:00", "%H:%M:%S").time())
        time_end = time_start + timedelta(minutes=minutes)
        stop_time = datetime.combine(date.today(), datetime.strptime(arrival_time, "%H:%M:%S").time())

        return time_start < stop_time < time_end

    def estimate_arrival(self, arrival_time: str) -> int:
        """Calculate how many minutes are left till vehicle departs."""

        # time_start = datetime.now()
        time_start = datetime.combine(date.today(), datetime.strptime("13:30:00", "%H:%M:%S").time())
        _arrival_time = datetime.combine(date.today(), datetime.strptime(arrival_time, "%H:%M:%S").time())

        delta = _arrival_time - time_start
        return int(delta.total_seconds() // 60)

    def poll(self, minutes: int) -> None:
        """Find upcoming arrivals for the query, that will occur within specified time window."""

        print("Polling...")

        matched_trips = []
        matched_trip_stops = []
        service = self.resolve_service_calendar()

        for trip in self._lookup["trips"].values():

            if trip.route_id != self.route.id:
                continue

            for stop_time in self._lookup["trip_stops"][trip.id].items:
                if (
                    trip.service_id == service.id
                    and self.stop.id == stop_time.stop_id
                    and self.check_arrival_within_window(stop_time.arrival_time, minutes=minutes)
                ):

                    matched_trips.append(trip)
                    matched_trip_stops.append(stop_time)

                    print(
                        f"Route: {self.route.id}\tDestination: {trip.headsign}\tStop: {self.stop.name} ({self.stop.code})\tPlanned arrival: {self.estimate_arrival(stop_time.arrival_time)} min"
                    )
