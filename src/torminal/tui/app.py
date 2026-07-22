"""TORminal TUI definition."""

import asyncio
from textual import work
from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, Static
from textual.containers import Grid
from httpx import ConnectTimeout, ConnectError
from collections import defaultdict
from datetime import datetime
from torminal.gtfs.static import GTFSStaticFeed
from torminal.query import Query, Monitor, RealtimePollResult
from torminal.config import config, Config
from torminal.gtfs.realtime import fetch_gtfs_rt_feed, fetch_peka_vm_feed
from torminal.tui.modals import LoadingScreen, QueryInput, get_markup_routes, get_markup_stops
from torminal.tui.widgets.bollard import Bollard
from torminal.requests import HTTPXCLIENT
from torminal.gtfs.realtime import GTFSRealTimeFeed, PEKARealTimeFeed
from torminal.gtfs.data import BollardMessage
import i18n


class TORminal(App):
    """A Textual GTFS dashboard app"""

    CSS_PATH = "style.tcss"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [
        ("a", "add_new", i18n.t("query_add")),
        ("r", "remove_stops", i18n.t("query_remove")),
        ("o", "options", i18n.t("app_options")),
        ("A", "about", i18n.t("app_about")),
        ("ctr+q", "quit", i18n.t("app_quit")),
    ]

    dataset: GTFSStaticFeed
    monitor: Monitor
    config: Config = config

    _peka_poll_interval: int = 60
    _gtfs_rt_poll_interval: int = 5
    _peka_cache: dict[str, PEKARealTimeFeed] = {}
    _gtfs_rt_cache: GTFSRealTimeFeed | None = None

    _bollards: dict[str, Bollard] = {}

    @work
    async def on_mount(self) -> None:
        self.theme = "gruvbox"
        self.title = "🚋 TORminal"
        self.sub_title = i18n.t("app_subtitle")

        self.dataset = await self.push_screen_wait(LoadingScreen())

        self.monitor = Monitor(self.dataset)
        await self.add_new_from_config()

        self._poll_peka()
        self._poll_gtfs_rt()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer(show_command_palette=False)

        yield Grid(classes="dashboard")

    @work
    async def _poll_gtfs_rt(self) -> None:
        """
        Get GTFS realtime feeds using interval determined by 'config.gtfs_rt_poll_interval'
        and prepare results.
        """
        while True:
            try:
                self._gtfs_rt_cache = await fetch_gtfs_rt_feed()
            except (ConnectTimeout, ConnectError):
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
            except (ConnectTimeout, ConnectError):
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
        if not self._gtfs_rt_cache:
            return

        results: dict[str, list[RealtimePollResult]] = defaultdict(list)
        for stop_code, poll_result in self.monitor.poll_all(self._gtfs_rt_cache, self._peka_cache):
            print(poll_result)
            results[stop_code].append(poll_result)

        for stop_code, polls in results.items():
            if bollard := self._bollards.get(stop_code):
                bollard.update_datatable(polls)
                bollard.update_message(polls[0].message)

    async def add_new_from_config(self) -> None:
        """Load queries from config and put them on dashboard"""

        for query in config.queries:
            await self._add_new(Query(query[0], query[1]))

    @work
    async def action_add_new(self) -> None:
        """An action to add new stop-route query to monitor."""

        # push query input modal screen
        stops = get_markup_stops(list(self.dataset.stops.values()))
        routes = get_markup_routes(list(self.dataset.routes.values()))
        stop_input, route_input = await self.push_screen_wait(QueryInput(stops, routes))

        if query := Query.from_input(stop_input, route_input):
            await self._add_new(query)

    async def _add_new(self, query: Query) -> None:
        """Add query to dashboard"""

        # update Monitor with the query
        self.monitor.add_query(query)

        # update dashboard
        stop = self.dataset.stops.get(query.stop_code)
        route = self.dataset.routes.get(query.route_id)

        # if Bollard for this stop already exists
        if bollard := self._bollards.get(stop.code, None):
            if route not in bollard.routes:
                bollard.routes.append(route)
            bollard.update_routes()
            return

        # if new Bollard needs to be added
        new_bollard = Bollard(stop)
        new_bollard.routes.append(route)
        self._bollards[stop.code] = new_bollard
        await self.dashboard.mount(new_bollard)

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

    @property
    def dashboard(self) -> Grid:
        return self.query_one(".dashboard", Grid)
