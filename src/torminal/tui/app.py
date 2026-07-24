"""TORminal TUI definition."""

import asyncio
from textual import work
from textual.app import App, ComposeResult
from textual.widgets import Footer, Header
from textual.containers import Grid
from httpx import ConnectTimeout, ConnectError
from collections import defaultdict
from torminal.gtfs.static import GTFSStaticFeed
from torminal.query import QueryKey, Monitor, RealtimePollResult
from torminal.config import config, Config
from torminal.gtfs.realtime import fetch_gtfs_rt_feed, fetch_peka_vm_feed
from torminal.tui.modals import LoadingScreen, QueryInput, QueryRemove, get_markup_routes, get_markup_stops
from torminal.tui.widgets.bollard import Bollard, UnavailableStop
from torminal.requests import HTTPXCLIENT
from torminal.gtfs.realtime import GTFSRealTimeFeed, PEKARealTimeFeed
from torminal.gtfs.data import Stop


class TORminal(App):
    """A Textual GTFS dashboard app"""

    CSS_PATH = "style.tcss"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [
        ("a", "add_new", "Add new query"),
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
    _autoscroll_active: bool = True
    _autoscroll_end_idle_interval: int = 3
    _autoscroll_interval: int = 0.5

    _bollards: dict[str, Bollard] = {}

    @work
    async def on_mount(self) -> None:
        # self._make_screenshot()

        self.theme = "gruvbox"
        self.title = "🚋 TORminal"
        self.sub_title = "public transport departures dashboard"

        self.dataset = await self.push_screen_wait(LoadingScreen())

        self.monitor = Monitor(self.dataset)
        await self.add_new_from_config()

        self._poll_peka()
        self._poll_gtfs_rt()
        self._autoscroll_handler()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer(show_command_palette=False)

        yield Grid(id="dashboard", classes="dashboard")

    @work
    async def _poll_gtfs_rt(self) -> None:
        """Get GTFS realtime feeds using interval determined by 'config.gtfs_rt_poll_interval' and prepare results."""
        while True:
            try:
                self._gtfs_rt_cache = await fetch_gtfs_rt_feed()
            except (ConnectTimeout, ConnectError):
                pass

            self._update_results()
            await asyncio.sleep(config.gtfs_rt_poll_interval)

    @work
    async def _make_screenshot(self) -> None:
        while True:
            self.save_screenshot(filename=None, path="screenshots/", time_format=None)
            await asyncio.sleep(5)

    @work
    async def _poll_peka(self) -> None:
        """Get PEKA virtual monitor feed using interval determined by 'config.peka_poll_interval' and prepare results."""
        while True:
            try:
                self._peka_cache = await self._fetch_all_peka()
            except (ConnectTimeout, ConnectError):
                pass

            self._update_results()
            await asyncio.sleep(config.peka_poll_interval)

    @work
    async def _autoscroll_handler(self) -> None:
        wgt = self.query_one("#dashboard")
        # seconds spent waiting at the extreme positions before resuming scroll again
        idle_counter = 0
        # true if going back up again
        reverse = False
        while True:
            if self._autoscroll_active:
                # detect edge positions
                at_edge = False
                if wgt.scroll_y + 1 > wgt.max_scroll_y:
                    reverse = True
                    at_edge = True
                elif wgt.scroll_y == 0:
                    reverse = False
                    at_edge = True
                if at_edge and idle_counter < self._autoscroll_end_idle_interval:
                    await asyncio.sleep(self._autoscroll_interval)
                    idle_counter += self._autoscroll_interval
                    continue
                if at_edge and idle_counter >= self._autoscroll_end_idle_interval:
                    idle_counter = 0

                if reverse:
                    wgt.scroll_up()
                else:
                    wgt.scroll_down()

            await asyncio.sleep(self._autoscroll_interval)

    async def _fetch_all_peka(self) -> dict[str, PEKARealTimeFeed]:
        """Fetch PEKA virtual monitor feeds for each stop in monitored queries."""
        peka_tasks = {
            stop_code: fetch_peka_vm_feed(self.dataset.stops_by_code.get(stop_code))
            for stop_code in self.monitor.queries
        }
        peka_results = await asyncio.gather(*peka_tasks.values())
        return dict(zip(peka_tasks.keys(), peka_results))

    def _update_results(self) -> None:
        if not self._gtfs_rt_cache:
            return

        results_by_stop: dict[str, list[RealtimePollResult]] = defaultdict(list)
        for stop_code, poll_result in self.monitor.poll_all(self._gtfs_rt_cache, self._peka_cache):
            results_by_stop[stop_code].append(poll_result)

        for stop_code, results in results_by_stop.items():
            if bollard := self._bollards.get(stop_code):
                bollard.update_datatable(results)
                bollard.update_message(results[0].message)

    async def add_new_from_config(self) -> None:
        """Load queries from config and put them on dashboard"""

        for query in config.queries:
            await self._add_new(QueryKey.from_config(query))

    @work
    async def action_add_new(self) -> None:
        """An action to add new stop-route query to monitor."""

        # push query input modal screen
        stops = get_markup_stops(list(self.dataset.stops.values()))
        routes = get_markup_routes(list(self.dataset.routes.values()))
        stop_input, route_input = await self.push_screen_wait(QueryInput(stops, routes))

        if query := QueryKey.from_input(stop_input, route_input):
            await self._add_new(query)

    async def _add_new(self, query: QueryKey) -> None:
        """Add query to dashboard"""

        self.monitor.add_query(query)

        # if Bollard for this stop already exists, just refresh its routes
        if bollard := self._bollards.get(query.stop_code):
            bollard.update_routes()
            return

        # if new Bollard needs to be added
        stop = self.dataset.stops_by_code.get(query.stop_code)
        if not stop:
            stop = UnavailableStop(query.stop_code)

        new_bollard = Bollard(stop, self.monitor)
        self._bollards[stop.code] = new_bollard
        await self.dashboard.mount(new_bollard)

    @work
    async def action_remove_stops(self) -> None:
        """An action to remove stops from the dashboard."""

        await self.push_screen_wait(QueryRemove(self.dataset.stops_by_code, self.monitor))
        await asyncio.sleep(0)

        queries = {query[0] for query in config.queries}
        for key, bollard in list(self._bollards.items()):
            if key in queries:
                bollard.update_routes()
            else:
                bollard.remove()
                self._bollards.pop(key)

        self.refresh(repaint=True, layout=True, recompose=True)
        # BUG: after removing all queries at once, TORminal might render footer blank and not respond,
        # the fix is to switch to another window and back. The solution could be rerendering the entire DOM,
        # but without using cached diff.

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
