from textual.app import ComposeResult
from textual.widgets import Label, ProgressBar, Button, Input
from textual.screen import ModalScreen
from textual.containers import Container, Vertical, Horizontal
from textual import work
from textual.content import Content
from textual_autocomplete import AutoComplete, DropdownItem

from torminal.gtfs.static import GTFSStaticLoader
from torminal.gtfs.static import ProgressEvent
from torminal.tui.widgets.spinner import Spinner
from torminal.gtfs.data import Route, Stop
from asyncio import sleep

import i18n

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
        self.modal.border_title = f" {i18n.t('init_modal')} "
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
    def __init__(self, stops: list[str], routes: list[str]) -> None:
        super().__init__()
        self.stops = [DropdownItem(main=Content.from_markup(s)) for s in stops]
        self.routes = [DropdownItem(main=Content.from_markup(r)) for r in routes]

    def compose(self) -> ComposeResult:
        stop_input = Input(placeholder=i18n.t("stop_add_code"), id="stop")
        route_input = Input(placeholder=i18n.t("stop_add_dest"), id="route")

        with Vertical(classes="box"):
            yield stop_input
            yield route_input

            yield AutoComplete(stop_input, candidates=self.stops)
            yield AutoComplete(route_input, candidates=self.routes)

            with Horizontal(classes="horizontal_buttons"):
                yield Button(i18n.t("action_add"), flat=True, id="add")
                yield Button(i18n.t("action_cancel"), flat=True, id="cancel")

    def on_mount(self) -> None:
        self.modal.border_title = f" {i18n.t('torminal.stop_add')} "
        self.modal.border_subtitle = " 🐐 "

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(("", ""))

        elif event.button.id == "add":
            self.dismiss((self.stop_input.value, self.route_input.value))

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
