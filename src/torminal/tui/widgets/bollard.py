import re
from typing import Any, Generator

from textual.reactive import reactive
from textual.widgets import Static, Label, DataTable, Link
from textual.containers import Vertical, Horizontal
from torminal.query import QueryMatch, RealtimePollResult, ArrivalTime
from torminal.gtfs.data import Stop, Route, BollardMessage, VehicleStatus
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


def format_eta(eta: int) -> str:
    """Get ETA minutes string formatted with unit and <, > information."""
    if eta < 1:
        return f'{"<1 min":>{eta_w}}'
    if eta > 60:
        return f'{">60 min":>{eta_w}}'
    return f"{f'{eta} min':>{eta_w}}"


def sort_eta(eta: str) -> int:
    """ETA value sorter function for datatable."""
    if eta.startswith("<"):
        return 0
    if eta.startswith(">"):
        return 61

    match = re.search(r"\d+", eta)
    return int(match.group()) if match else 999


def format_status(status: VehicleStatus) -> str | Content:
    """Get formatted status string."""
    match status:
        case VehicleStatus.ON_TIME:
            return f"{f'🛜':^{status_w}}"
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
            return f"{f'🛜':^{status_w}}"
        case VehicleStatus.NO_RT:
            return ""


def format_title(stop: Stop | str) -> Content:
    """Prepare formatted stop data string to be used in Bollard's border title."""
    if isinstance(stop, Stop):
        return Content.from_markup(f"[italic]({stop.code})[/] {stop.name}")
    else:
        return Content.from_markup(f"[italic]({stop})[/] Stop unavailable")


def format_routes(routes: list[Route | str]) -> Content:
    """Prepare string of comma-separated route IDs and colored depending on being resolved into Route objects or not."""
    _formatted_routes = []
    for route in routes:
        if isinstance(route, Route):
            _formatted_routes.append(route.id)
        else:
            _formatted_routes.append(Content.from_markup(f"[$text 50%]{route.id}[/]"))
    return ", ".join(_formatted_routes)


def format_delay(arrival_time: ArrivalTime) -> str:
    """Get delay string with units"""
    sign = "+" if arrival_time.delay > 0 else ""
    delay_min = arrival_time.delay // 60
    delay = delay_min if delay_min < 99 else 99
    if delay > 5:
        return f"{sign}[$warning bold]{delay}[/] min"
    return f"{sign}{delay} min"


class Bollard(Vertical):
    """Widget representing bollard gathering informations from a single stop"""

    def __init__(self, stop: Stop | str, routes: list[Route | str] = []) -> None:
        super().__init__()
        self.stop = stop
        self.routes: list[Route] = []

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

        # hide bollard info t init
        self.message_label.display = False
        self.message_link.display = False

        # update stop and routes data
        self.border_title = format_title(self.stop)
        self.update_routes()

    def update_routes(self) -> None:
        """Update text displayed in Routes: label, uses Routes stored in 'self.routes'"""

        self.routes_label.content = f"Routes: {format_routes(self.routes)}" if self.routes else ""

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
                    format_eta(eta),
                    (
                        format_delay(poll.realtime_arrival)
                        if poll.realtime_arrival and is_off_schedule(poll.status)
                        else format_status(poll.status)
                    ),
                    poll.destination,
                )
            )

        self.table.add_rows(rows)
        self.table.sort("eta", key=sort_eta)
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
