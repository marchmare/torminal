import webbrowser
import re
from typing import Any, Generator

from textual.reactive import reactive
from textual.widgets import Static, Label, DataTable, Link
from textual.containers import Vertical, Horizontal
from torminal.query import QueryMatch, RealtimePollResult
from torminal.gtfs.data import Stop, Route, BollardMessage
from textual.content import Content

TEMPLATE = [
    ("3", "20:35", "  6 min", "DELAY", "Błażeja"),
    ("10", "20:54", " 34 min", "STUCK", "Błażeja"),
    ("167", "20:24", "  2 min", "⦾", "Radjewo"),
    ("10", "20:56", ">60 min", "EARLY", "Błażeja"),
    ("10", "20:56", " 24 min", "", "Błażeja"),
    ("167", "20:24", " <1 min", "DETOUR", "Radjewo"),
]

COLUMNS = [
    ("Route", "route", 5),
    ("Time", "time", 5),
    ("    ETA", "eta", 7),
    ("Status", "status", 6),
    ("Destination", "destination", None),
]


class Bollard(Vertical):
    """Widget representing bollard gathering informations from a single stop"""

    def __init__(self, stop: Stop) -> None:
        super().__init__()
        self.stop = stop
        self.routes: list[Route] = []

    def action_open_url(self, url: str) -> None:
        webbrowser.open(url)

    def update_datatable(self, query: list[QueryMatch], poll: list[RealtimePollResult]) -> None:
        pass

    def set_stop_title(self) -> None:
        """Update text displayed in Bollard border title"""

        self.border_title = Content.from_markup(f"([italic $background]{self.stop.code}[/]) {self.stop.name}")

    def update_routes(self) -> None:
        """Update text displayed in Routes: label. Pass empty list to hide."""

        routes_str = [route.id for route in self.routes]
        self.routes_label.content = f"Routes: {', '.join(routes_str)}" if self.routes else ""

    def update_message(self, message: BollardMessage | None = None) -> None:
        """Update text displayed in message label with link. Pass None to hide."""

        self.message_label.display = self.message_link.display = message is not None

        if message:
            self.message_link.url = message.link
            self.message_label.content = message.messagee

    def compose(self) -> Generator[Label, Any, None]:
        yield Label(classes="routes")
        yield DataTable()
        yield Label(classes="info", id="info_label")
        yield Link("[link]", classes="info", id="info_link")

    def on_mount(self) -> None:
        self.table.cursor_type = "row"

        self.message_label.display = False
        self.message_link.display = False

        for column in COLUMNS:
            self.table.add_column(column[0], key=column[1], width=column[2])

        self.table.add_rows(TEMPLATE)
        self.table.sort("eta", key=self._eta_sort)

        self.set_stop_title()
        self.update_message()
        self.update_routes()

    def _eta_sort(self, eta: str) -> int:
        if eta.startswith("<"):
            return 0
        if eta.startswith(">"):
            return 61

        match = re.search(r"\d+", eta)
        return int(match.group()) if match else 999

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
