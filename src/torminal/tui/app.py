"""TORminal TUI definition."""

import asyncio
from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, Input, Button
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual_autocomplete import AutoComplete, DropdownItem
from torminal.gtfs.static import GTFSStaticFeed
from torminal.query import Query, Monitor
from torminal.config import config, Config
from torminal.gtfs.realtime import fetch_gtfs_rt_feed, fetch_peka_vm_feed
from torminal.tui.loadingscreen import LoadingScreen
from torminal.requests import HTTPXCLIENT
from textual import work


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

    @work
    async def on_mount(self) -> None:
        self.theme = "gruvbox"
        self.title = "🚋 TORminal"
        self.sub_title = "public transport departures dashboard"

        self.dataset = await self.push_screen_wait(LoadingScreen())

        self.monitor = Monitor(self.dataset)
        self.monitor.add_query(Query("NARA71", "214"))

        self.poll_loop()

    @work(exclusive=True)
    async def poll_loop(self) -> None:
        """Recurring poll loop"""

        while True:
            await self.poll()
            await asyncio.sleep(30)

    async def poll(self) -> None:
        print("Polling...")

        peka_tasks = {
            stop: fetch_peka_vm_feed(self.monitor.dataset.stops.get(stop)) for stop in self.monitor.matched_queries
        }
        peka_results = await asyncio.gather(*peka_tasks.values())
        peka_feeds = dict(zip(peka_tasks.keys(), peka_results))

        rt_gtfs = await fetch_gtfs_rt_feed()

        for stop, stop_matches in self.monitor.matched_queries.items():
            rt_msg = peka_feeds[stop]

            for match in stop_matches:
                rt_tu = rt_gtfs.trip_updates.get(match.trip.id, None)
                rt_vp = rt_gtfs.vehicle_positions.get(match.trip.id, None)

                result = self.monitor.poll(match, rt_tu, rt_vp, rt_msg)
                print(result)

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

    async def on_exit(self) -> None:
        await HTTPXCLIENT.aclose()
