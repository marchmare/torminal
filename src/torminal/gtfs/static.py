from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from torminal.gtfs.static import GTFSStaticFeed

import asyncio
import csv
import io
from collections.abc import Awaitable, Mapping
from collections import defaultdict
from typing import Callable, TypeVar
from dataclasses import dataclass, field
from io import TextIOWrapper
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from torminal.gtfs.gps import shape_to_path
from torminal.requests import fetch_gtfs_zip, fetch_vehicle_dictionary, open_gtfs_zip, open_vehicle_dictionary
from torminal.gtfs.data import (
    Trip,
    Route,
    Stop,
    TripStops,
    Shape,
    FeedInfo,
    ServiceCalendar,
    Vehicle,
    GroupModel,
    Model,
    StopTime,
)

StopRouteIndex = Mapping[str, Mapping[str, list[tuple[Trip, StopTime]]]]


@dataclass
class GTFSStaticFeed:
    vehicles: dict[str, Vehicle]
    trips: dict[str, Trip]
    routes: dict[str, Route]
    stops: dict[str, Stop]  # stops by ID
    shapes: dict[str, Shape]
    service_calendars: dict[str, ServiceCalendar]
    feed_info: FeedInfo
    _trip_stops: dict[str, TripStops] = field(init=True, repr=False)  # deleted in build_indices()
    stops_by_code: dict[str, Stop] = field(init=False)
    stop_route_index: dict[Stop, dict[Route, tuple[Trip, StopTime]]] = field(init=False)

    def build_indices(self) -> None:
        """
        Build derived lookup indices, runs in separate threads and is to be called with async wrapper,
        so it can't be __post_init__.
        """

        with ThreadPoolExecutor(max_workers=3) as pool:
            f_stops = pool.submit(self._build_stops_by_code)
            f_times = pool.submit(self._remap_stop_times)
            f_index = pool.submit(self._build_stop_route_index)

        f_times.result()
        self.stops_by_code = f_stops.result()
        self.stop_route_index = f_index.result()

        del self._trip_stops

    def _build_stops_by_code(self) -> dict[str, Stop]:
        """Thread creating lookup of Stops using stop code key."""
        return {stop.code: stop for stop in self.stops.values()}

    def _remap_stop_times(self) -> None:
        """Thread assigning StopTimes items to related Trip."""
        for trip in self.trips.values():
            if trip_stops := self._trip_stops.get(trip.id):
                trip.stop_times = trip_stops.items

    def _build_stop_route_index(self) -> StopRouteIndex:
        """
        Thread creating lookup for stop-route pairs, returning tuples of (Trip, StopTime).
        Stops are indexed by code.
        """

        def create_route_index() -> defaultdict[str, list[tuple[Trip, StopTime]]]:
            return defaultdict(list)

        index: StopRouteIndex = defaultdict(create_route_index)

        for trip in self.trips.values():

            route = self.routes.get(trip.route_id)
            trip_stops = self._trip_stops.get(trip.id)

            if not route or not trip_stops:
                continue
            for stop_time in trip_stops.items:
                stop = self.stops.get(stop_time.stop_id)

                if not stop:
                    continue

                index[stop.code][route.id].append((trip, stop_time))

        return index


@dataclass
class ProgressEvent:
    """Loader progress data for passing via callbacks."""

    current: int
    total: int
    message: str

    def __repr__(self) -> str:
        return f"{self.current}/{self.total}\t{self.message}"


class GTFSStaticLoader:
    """Loader for GTFS static data with progress tracking."""

    def __init__(self, progress_callback: Callable[[ProgressEvent], None]) -> None:
        self.callback: Callable[[ProgressEvent], None] = progress_callback
        self.current = 0
        self.total: int = 12

    def emit_progress(self, message: str) -> None:
        """Execute callback function with ProgressEvent"""
        print(message)
        self.callback(ProgressEvent(current=self.current, total=self.total, message=message))

    async def track(self, task: Awaitable, message: str):
        """Track progress of an awaitable task."""
        result = await task
        self.current += 1
        self.emit_progress(message)
        return result

    async def load(self) -> GTFSStaticFeed:
        """Load GTFS static data."""

        # fetch static data sources
        await asyncio.gather(
            self.track(fetch_vehicle_dictionary(), "Downloaded vehicle_dictionary.csv"),
            self.track(fetch_gtfs_zip(), "Downloaded GTFS archive"),
        )

        # parse into dataset
        with open_vehicle_dictionary() as vd, open_gtfs_zip() as z:
            # ZipFile is not thread-safe - read all bytes first
            raw_trips = z.read(Trip._gtfs_file)
            raw_trip_stops = z.read(TripStops._gtfs_file)
            raw_routes = z.read(Route._gtfs_file)
            raw_stops = z.read(Stop._gtfs_file)
            raw_shapes = z.read(Shape._gtfs_file)
            raw_calendar = z.read(ServiceCalendar._gtfs_file)
            raw_feed_info = z.read(FeedInfo._gtfs_file)

            # pass raw bytes to worker threads.
            results = await asyncio.gather(
                self.track(asyncio.to_thread(parse_vehicle_dictionary, vd), "Parsed vehicle_dictionary.csv"),
                self.track(asyncio.to_thread(parse_txt_as_dict, Trip, raw_trips), "Parsed trips.txt"),
                self.track(
                    asyncio.to_thread(parse_txt_as_dict_grouped, TripStops, raw_trip_stops), "Parsed trip_stops.txt"
                ),
                self.track(asyncio.to_thread(parse_txt_as_dict, Route, raw_routes), "Parsed routes.txt"),
                self.track(asyncio.to_thread(parse_txt_as_dict, Stop, raw_stops), "Parsed stops.txt"),
                self.track(asyncio.to_thread(parse_txt_as_dict_grouped, Shape, raw_shapes), "Parsed shapes.txt"),
                self.track(asyncio.to_thread(parse_txt_as_dict, ServiceCalendar, raw_calendar), "Parsed service.txt"),
                self.track(asyncio.to_thread(parse_feed_info, raw_feed_info), "Parsed feed_info.txt"),
            )

        vehicles, trips, trip_stops, routes, stops, shapes, service_calendars, feed_info = results

        await self.track(asyncio.to_thread(build_all_polygons, shapes), "Built trip shape polygons")

        gtfs_static_lookup = GTFSStaticFeed(
            vehicles=vehicles,
            trips=trips,
            _trip_stops=trip_stops,
            routes=routes,
            stops=stops,
            shapes=shapes,
            service_calendars=service_calendars,
            feed_info=feed_info,
        )

        await self.track(asyncio.to_thread(gtfs_static_lookup.build_indices), "Built derived lookup indices")

        return gtfs_static_lookup


M = TypeVar("M", bound=Model)
G = TypeVar("G", bound=GroupModel)


def build_all_polygons(shapes: dict[str, Shape]) -> None:
    """Build and assign buffered path for a Shape from its items."""
    for shape in shapes.values():
        shape.path = shape_to_path(shape.items)


def read_gtfs_df(raw: bytes) -> pd.DataFrame:
    """Read a GTFS text file into a DataFrame, keeping every cell as a string."""
    return pd.read_csv(io.BytesIO(raw), encoding="utf-8-sig", dtype=str, keep_default_na=False)


def parse_txt_as_dict(model: type[M], raw: bytes) -> dict[str, M]:
    """
    Parse a GTFS text file into a dictionary indexed by a unique key.

    Intended for files where the key column acts as a primary key and
    each key corresponds to a single record.
    """
    return model.from_df(read_gtfs_df(raw))


def parse_txt_as_dict_grouped(model: type[G], raw: bytes) -> dict[str, G]:
    """
    Parse a GTFS text file into a dictionary grouped by a key column.

    Intended for files where multiple records share the same key,
    representing a one-to-many relationship.
    """
    return model.from_df(read_gtfs_df(raw))


def parse_vehicle_dictionary(raw: bytes) -> dict[str, Vehicle]:
    """
    Returns dictionary of vehicle ID: Vehicle.
    This file stores info about specific vehicle type and features.

         Documentation: https://www.ztm.poznan.pl/wp-content/uploads/2024/07/slownik-pojazdow-opis.pdf
    """
    return Vehicle.from_df(read_gtfs_df(raw))


def parse_feed_info(raw: bytes) -> FeedInfo:
    """
    Parse feed_info.txt.
    """
    with TextIOWrapper(io.BytesIO(raw), encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        row = next(reader)
        return FeedInfo.from_dict(row)
