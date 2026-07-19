"""TORminal TUI definition."""

import asyncio
from datetime import datetime
from collections import defaultdict
from textual import work
from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, Input, Button
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual_autocomplete import AutoComplete, DropdownItem
from httpx import ConnectTimeout

from torminal.gtfs.static import GTFSStaticFeed
from torminal.query import Query, Monitor
from torminal.config import config, Config
from torminal.gtfs.realtime import fetch_gtfs_rt_feed, fetch_peka_vm_feed
from torminal.tui.loadingscreen import LoadingScreen
from torminal.requests import HTTPXCLIENT
from torminal.gtfs.realtime import GTFSRealTimeFeed, PEKARealTimeFeed


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

    _peka_poll_interval: int = 60
    _gtfs_rt_poll_interval: int = 5
    _peka_cache: dict[str, PEKARealTimeFeed] = {}
    _gtfs_rt_cache: GTFSRealTimeFeed | None = None

    @work
    async def on_mount(self) -> None:
        self.theme = "gruvbox"
        self.title = "🚋 TORminal"
        self.sub_title = "public transport departures dashboard"

        self.dataset = await self.push_screen_wait(LoadingScreen())

        self.monitor = Monitor(self.dataset)
        self.monitor.add_query(Query("NARA71", "214"))
        self.monitor.add_query(Query("NARA71", "3"))
        self.monitor.add_query(Query("NARA71", "10"))

        self._poll_peka()
        self._poll_gtfs_rt()

    @work
    async def _poll_gtfs_rt(self) -> None:
        """
        Get GTFS realtime feeds using interval determined by 'config.gtfs_rt_poll_interval'
        and prepare results.
        """
        while True:
            try:
                self._gtfs_rt_cache = await fetch_gtfs_rt_feed()
            except ConnectTimeout:
                pass

            self._update_results()
            await asyncio.sleep(config.gtfs_rt_poll_interval)

    @work
    async def _poll_peka(self) -> None:
        """
        Get PEKA virtual monitor feed using interval determined by 'config.peka_poll_interval'
        and prepare results.
        """
        while True:
            try:
                self._peka_cache = await self._fetch_all_peka()
            except ConnectTimeout:
                pass

            self._update_results()
            await asyncio.sleep(config.peka_poll_interval)

    async def _fetch_all_peka(self) -> dict[str, PEKARealTimeFeed]:
        """Helper method to prepare dictionary of PEKA feeds for each stop in matched queries"""
        peka_tasks = {
            stop: fetch_peka_vm_feed(self.monitor.dataset.stops.get(stop)) for stop in self.monitor.matched_queries
        }
        peka_results = await asyncio.gather(*peka_tasks.values())
        return dict(zip(peka_tasks.keys(), peka_results))

    def _update_results(self) -> None:
        """Gather feeds and prepare a result."""
        if not self._gtfs_rt_cache:
            return

        for result in self.monitor.poll_all(self._gtfs_rt_cache, self._peka_cache):
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
