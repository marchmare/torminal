from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Generator

from textual.widgets import Label, DataTable, Link
from textual.containers import Vertical
from torminal.query import RealtimePollResult, ArrivalTime
from torminal.gtfs.data import Stop, Route, BollardMessage, VehicleStatus

if TYPE_CHECKING:
    from torminal.query import Monitor

from textual.content import Content

route_w = 5
time_w = 5
eta_w = 7
status_w = 7

COLUMNS = [
    ("Route", "route", route_w),
    ("Time", "time", time_w),
    (f"{'ETA':>{eta_w}}", "eta", eta_w),
    ("Status", "status", status_w),
    ("Destination", "destination", None),
]


class UnavailableStop:
    """Empty stop to use when Stop is not found in the dataset."""

    def __init__(self, code: str) -> None:
        self.id: str = "n/a"
        self.code: str = code
        self.name: str = "Stop unavailable"


class Bollard(Vertical):
    """Widget representing bollard gathering informations from a single stop"""

    def __init__(self, stop: Stop | UnavailableStop, monitor: Monitor) -> None:
        super().__init__()
        self.stop = stop
        self.monitor = monitor

    def compose(self) -> Generator[Label, Any, None]:
        yield Label(classes="routes")
        yield DataTable()
        yield Label(classes="info", id="info_label")
        yield Link("[link]", classes="info", id="info_link")

    def on_mount(self) -> None:
        # define datatable
        for column in COLUMNS:
            self.table.add_column(column[0], key=column[1], width=column[2])
        self.table.cursor_type = "row"

        # hide bollard info on init
        self.message_label.display = False
        self.message_link.display = False

        # update stop and routes data
        self.border_title = self.format_title(self.stop)
        self.update_routes()
        if isinstance(self.stop, UnavailableStop):
            self.disabled = True

    def update_routes(self) -> None:
        """Update text displayed in Routes label, derived from monitor's queries mapping."""
        route_ids = self.monitor.queries.get(self.stop.code, {})
        self.routes_label.content = self.format_routes(route_ids)

    def update_datatable(self, polls: list[RealtimePollResult]) -> None:
        """
        Update rows in datatable using Realtime poll results for the specific Stop.
        To be called as Monitor's poll callback.
        """

        def is_off_schedule(status: VehicleStatus) -> bool:
            return status in [VehicleStatus.DELAYED, VehicleStatus.SLIGHTLY_DELAYED, VehicleStatus.EARLY]

        def is_rt_satus_unavailable(status: VehicleStatus) -> bool:
            return status in [VehicleStatus.NO_RT, VehicleStatus.AT_TERMINUS]

        _cursor = self.table.cursor_coordinate
        self.table.clear()

        rows = []
        for poll in polls:
            eta = (
                poll.planned_arrival.eta
                if not poll.realtime_arrival and is_rt_satus_unavailable(poll.status)
                else poll.realtime_arrival.eta
            )
            rows.append(
                (
                    poll.route_id,
                    poll.planned_arrival.time.strftime("%H:%M"),
                    self.format_eta(eta),
                    (
                        self.format_delay(poll.realtime_arrival)
                        if poll.realtime_arrival and is_off_schedule(poll.status)
                        else self.format_status(poll.status)
                    ),
                    poll.destination,
                )
            )

        self.table.add_rows(rows)
        self.table.sort("eta", key=self.sort_eta)
        self.table.cursor_coordinate = _cursor

    def update_message(self, message: BollardMessage | None = None) -> None:
        """
        Update text displayed in message label with link. Pass None to hide.
        To be called as Monitor's poll callback.
        """

        self.message_label.display = self.message_link.display = message is not None
        if message:
            self.message_link.url = message.link
            self.message_label.content = message.message

    @property
    def table(self) -> DataTable:
        return self.query_one(DataTable)

    @property
    def message_link(self) -> Link:
        return self.query_one("#info_link", Link)

    @property
    def message_label(self) -> Label:
        return self.query_one("#info_label", Label)

    @property
    def routes_label(self) -> Label:
        return self.query_one(".routes", Label)

    @staticmethod
    def format_eta(eta: int) -> str:
        """Get ETA minutes string formatted with unit and <, > information."""
        if eta < 1:
            return f'{"<1 min":>{eta_w}}'
        if eta > 60:
            return f'{">60 min":>{eta_w}}'
        return f"{f'{eta} min':>{eta_w}}"

    @staticmethod
    def sort_eta(eta: str) -> int:
        """ETA value sorter function for datatable."""
        if eta.startswith("<"):
            return 0
        if eta.startswith(">"):
            return 61

        match = re.search(r"\d+", eta)
        return int(match.group()) if match else 999

    @staticmethod
    def format_status(status: VehicleStatus) -> str | Content:
        """Get formatted status string."""
        match status:
            case VehicleStatus.ON_TIME:
                return f"{f'((o))':^{status_w}}"
            case VehicleStatus.SLIGHTLY_DELAYED:
                return Content.from_markup("DELAY")
            case VehicleStatus.DELAYED:
                return Content.from_markup("[bold]DELAY[/]")
            case VehicleStatus.EARLY:
                return Content.from_markup("EARLY")
            case VehicleStatus.DETOURED:
                return Content.from_markup("[bold]DETOUR[/]")
            case VehicleStatus.STUCK:
                return Content.from_markup("[bold]STUCK[/]")
            case VehicleStatus.AT_TERMINUS:
                return f"{f'((o))':^{status_w}}"
            case VehicleStatus.NO_RT:
                return ""

    @staticmethod
    def format_title(stop: Stop | UnavailableStop) -> Content:
        """Prepare formatted stop data string to be used in Bollard's border title."""

        return Content.from_markup(f"[italic]({stop.code})[/] {stop.name}")

    def format_routes(self, routes: list[str]) -> Content:
        """Prepare string of comma-separated route IDs and colored depending on being resolved into Route objects or not."""
        _formatted_routes = []
        for route in routes:
            if self.monitor.validate_stop_on_route(self.stop.code, route):
                print(f"Route {route} belongs on {self.stop}")
                _formatted_routes.append(route)
            else:
                print(f"Route {route} doesn't belong on {self.stop}")
                _formatted_routes.append(f"[$text 25%]{route}[/]")

        return Content.from_markup(f"Routes: {", ".join(_formatted_routes)}") if routes else ""

    @staticmethod
    def format_delay(arrival_time: ArrivalTime) -> str:
        """Get delay string with units"""
        sign = "+" if arrival_time.delay > 0 else ""
        delay_min = arrival_time.delay // 60
        delay = delay_min if delay_min < 99 else 99
        if delay > 5:
            return Content.from_markup(f"[$warning bold]{sign}{delay} min[/]")
        return f"{sign}{delay} min"
