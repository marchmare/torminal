"""TORminal TUI definition."""

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, Input, Button
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual_autocomplete import AutoComplete, DropdownItem
from torminal.gtfs.static import GTFSStaticFeed
from torminal.query import Query, Monitor
from torminal.config import config, Config

from torminal.tui.loadingscreen import LoadingScreen


class TORminal(App):
    """A Textual GTFS dashboard app"""

    CSS_PATH = "style.tcss"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [
        ("a", "add_new_stop", "Add new stop"),
        ("r", "remove_stops", "Remove stops"),
        ("o", "options", "Options"),
        ("A", "about", "About"),
        ("ctr+q", "quit", "Quit"),
    ]

    dataset: GTFSStaticFeed
    monitor: Monitor
    config: Config = config

    def on_mount(self) -> None:
        self.theme = "gruvbox"
        self.title = "🚋 TORminal"
        self.sub_title = "public transport departures dashboard"

        self.dataset = self.push_screen(LoadingScreen())

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer(show_command_palette=False)

    def action_add_new_stop(self) -> None:
        """An action to add new stop-route query to monitor."""
        pass

    def action_remove_selected(self) -> None:
        """An action to remove selected query from the dashboard."""
        pass

    def action_edit_selected(self) -> None:
        """An action to edit selected query in the dashboard."""
        pass

    def action_options(self) -> None:
        """An action to display settings dialog."""
        pass

    def action_about(self) -> None:
        """An action to display About TORminal."""
        pass
