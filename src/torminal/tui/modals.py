from textual.app import ComposeResult
from textual.widgets import Label, ProgressBar, Button, Input, DataTable
from textual.screen import ModalScreen
from textual.containers import Container, Vertical, Horizontal
from textual import work
from textual.content import Content
from textual_autocomplete import AutoComplete, DropdownItem

from torminal.config import config
from torminal.gtfs.static import GTFSStaticLoader
from torminal.gtfs.static import ProgressEvent
from torminal.tui.widgets.spinner import Spinner
from torminal.gtfs.data import Route, Stop
from torminal.query import Monitor, QueryKey
from asyncio import sleep

LOGO = """░▀█▀░█▀█░█▀▄░█▄█░▀█▀░█▀█░█▀█░█░░░
░░█░░█░█░█▀▄░█░█░░█░░█░█░█▀█░█░░░
░░▀░░▀▀▀░▀░▀░▀░▀░▀▀▀░▀░▀░▀░▀░▀▀▀░"""


class LoadingScreen(ModalScreen):
    def compose(self) -> ComposeResult:
        with Container(classes="box"):
            yield Label(LOGO)
            yield Label("", id="loading_message")
            yield Spinner()
            yield ProgressBar(show_eta=False, show_percentage=False)

    def on_mount(self) -> None:
        self.modal.border_title = " Initializing "
        self.modal.border_subtitle = " 🐐 "

        self.load_data()

    @work
    async def load_data(self) -> None:
        """Main loader worker, initializes loader and progress bar, then loads GTFS static data."""

        loader = GTFSStaticLoader(self.update_progress)
        self.bar.update(total=loader.total)

        data = await loader.load()
        await sleep(0.25)

        self.dismiss(data)

    def update_progress(self, progress: ProgressEvent) -> None:
        """Update progress bar and loading message label state."""

        self.loading_message.update(progress.message)
        self.bar.animate("progress", progress.current, duration=0.3)

    @property
    def modal(self) -> Label:
        return self.query_one(".box", Container)

    @property
    def bar(self) -> ProgressBar:
        return self.query_one(ProgressBar)

    @property
    def loading_message(self) -> Label:
        return self.query_one("#loading_message", Label)


def get_markup_stops(stops: list[Stop]) -> list[str]:
    """Helper function, prepare formatted list of route strings to use for autocompletion."""
    return [f"[bold $text on $accent 50%]({stop.code:>7})[/] {stop.name}" for stop in stops]


def get_markup_routes(routes: list[Route]) -> list[str]:
    """Helper function, prepare formatted list of route strings to use for autocompletion."""
    return [f"[bold $text on $accent 50%]({route.id:>3})[/] {route.long_name.split('|')[0]}" for route in routes]


class QueryInput(ModalScreen):

    BINDINGS = [
        ("escape", "back", "Back"),
    ]

    def __init__(self, stops: list[str], routes: list[str]) -> None:
        super().__init__()
        self.stops = [DropdownItem(main=Content.from_markup(s)) for s in stops]
        self.routes = [DropdownItem(main=Content.from_markup(r)) for r in routes]

    def compose(self) -> ComposeResult:
        stop_input = Input(placeholder="Stop name or code", id="stop")
        route_input = Input(placeholder="Route number or destination", id="route")

        with Vertical(classes="box"):
            yield stop_input
            yield route_input

            yield AutoComplete(stop_input, candidates=self.stops)
            yield AutoComplete(route_input, candidates=self.routes)

            with Horizontal(classes="horizontal_buttons"):
                yield Button("Add", flat=True, id="add")
                yield Button("Cancel", flat=True, id="cancel")

    def on_mount(self) -> None:
        self.modal.border_title = " Add new stop "
        self.modal.border_subtitle = " 🐐 "

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(("", ""))

        elif event.button.id == "add":
            self.dismiss((self.stop_input.value, self.route_input.value))

    def action_back(self) -> None:
        self.dismiss(("", ""))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.screen.focus_next()

    @property
    def modal(self) -> Label:
        return self.query_one(".box", Vertical)

    @property
    def route_input(self) -> Label:
        return self.query_one("#route", Input)

    @property
    def stop_input(self) -> Label:
        return self.query_one("#stop", Input)

    @property
    def button_add(self) -> Button:
        return self.query_one("#add", Button)

    @property
    def button_cancel(self) -> Button:
        return self.query_one("#cancel", Button)


class QueryRemove(ModalScreen):
    BINDINGS = [
        ("escape", "back", "Back"),
        ("delete", "remove", "Remove"),
    ]

    stop_code_w = 9
    stop_name_w = 30
    route_w = 5

    COLUMNS = [
        ("Stop code", "stop_code", stop_code_w),
        (f"{'Stop name':<{stop_name_w}}", "stop_name", stop_name_w),
        (f"{'Route':<{route_w}}", "route", route_w),
    ]

    def __init__(self, stops: dict[str, Stop], monitor: Monitor) -> None:
        super().__init__()
        self.stops = stops
        self.monitor = monitor

    def compose(self) -> ComposeResult:
        with Container(classes="box"):
            yield DataTable()
            with Horizontal(classes="horizontal_buttons"):
                yield Button("Remove", flat=True, id="remove")
                yield Button("Remove all", flat=True, id="remove_all")
                yield Button("Back", flat=True, id="cancel")

    def on_mount(self) -> None:
        self.modal.border_title = " Remove stops "
        self.modal.border_subtitle = " 🐐 "

        for column in QueryRemove.COLUMNS:
            self.table.add_column(column[0], key=column[1], width=column[2])
        self.table.cursor_type = "row"

        for query in config.queries:
            stop_name = ""
            if stop := self.stops.get(query[0], None):
                stop_name = stop.name
            self.table.add_row(query[0], stop_name, query[1], key=f"{query[0]}{query[1]}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss()

        elif event.button.id == "remove_all":
            for i in range(self.table.row_count):
                row = self.table.get_row_at(i)
                query = QueryKey(row[0], row[2])
                self.monitor.remove_query(query)
            self.table.clear()

        elif event.button.id == "remove":
            row_index = self.table.cursor_row
            row = self.table.get_row_at(row_index)

            query = QueryKey(row[0], row[2])

            self.monitor.remove_query(query)
            self.table.remove_row(f"{query.stop_code}{query.route_id}")

    def action_back(self) -> None:
        self.dismiss()

    @property
    def modal(self) -> Label:
        return self.query_one(".box", Container)

    @property
    def table(self) -> DataTable:
        return self.query_one(DataTable)

    @property
    def button_remove(self) -> Button:
        return self.query_one("#remove", Button)

    @property
    def button_remove_all(self) -> Button:
        return self.query_one("#remove_all", Button)

    @property
    def button_cancel(self) -> Button:
        return self.query_one("#cancel", Button)
