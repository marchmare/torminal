import csv
import asyncio
from collections.abc import Awaitable
from typing import Callable, TypeVar
from dataclasses import dataclass
from csv import DictReader
from zipfile import ZipFile
from io import TextIOWrapper

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
)


@dataclass
class GTFSStaticFeed:
    vehicles: dict[str, Vehicle]
    trips: dict[str, Trip]
    trip_stops: dict[str, TripStops]
    routes: dict[str, Route]
    stops: dict[str, Stop]
    shapes: dict[str, Shape]
    service_calendars: dict[str, ServiceCalendar]
    feed_info: FeedInfo


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
        self.total: int = 10

    def emit_progress(self, message: str) -> None:
        """Execute callback function with ProgressEvent"""
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
            results = await asyncio.gather(
                self.track(asyncio.to_thread(parse_vehicle_dictionary, vd), "Parsed vehicle_dictionary.csv"),
                self.track(asyncio.to_thread(parse_txt_as_dict, Trip, z), "Parsed trips.txt"),
                self.track(asyncio.to_thread(parse_txt_as_dict_grouped, TripStops, z), "Parsed trip_stops.txt"),
                self.track(asyncio.to_thread(parse_txt_as_dict, Route, z), "Parsed routes.txt"),
                self.track(asyncio.to_thread(parse_txt_as_dict, Stop, z), "Parsed stops.txt"),
                self.track(asyncio.to_thread(parse_txt_as_dict_grouped, Shape, z), "Parsed shapes.txt"),
                self.track(asyncio.to_thread(parse_txt_as_dict, ServiceCalendar, z), "Parsed service.txt"),
                self.track(asyncio.to_thread(parse_feed_info, z), "Parsed feed_info.txt"),
            )

        vehicles, trips, trip_stops, routes, stops, shapes, service_calendars, feed_info = results

        gtfs_static_lookup = GTFSStaticFeed(
            vehicles=vehicles,
            trips=trips,
            trip_stops=trip_stops,
            routes=routes,
            stops=stops,
            shapes=shapes,
            service_calendars=service_calendars,
            feed_info=feed_info,
        )
        return gtfs_static_lookup


M = TypeVar("M", bound=Model)
G = TypeVar("G", bound=GroupModel)


def parse_txt_as_dict(model: type[M], z: ZipFile) -> dict[str, M]:
    """
    Parse a GTFS text file into a dictionary indexed by a unique key.

    Intended for files where the key column acts as a primary key and
    each key corresponds to a single record.
    """
    with z.open(model._gtfs_file) as f:
        reader = csv.DictReader(TextIOWrapper(f, encoding="utf-8-sig"))
        return {row[model._key]: model.from_dict(row) for row in reader}


def parse_txt_as_dict_grouped(model: type[G], z: ZipFile) -> dict[str, G]:
    """
    Parse a GTFS text file into a dictionary grouped by a key column.

    Intended for files where multiple records share the same key,
    representing a one-to-many relationship.
    """
    with z.open(model._gtfs_file) as f:
        reader = csv.DictReader(TextIOWrapper(f, encoding="utf-8-sig"))
        _dict: dict[str, G] = {}

        for row in reader:
            if row[model._key] not in _dict:
                _dict[row[model._key]] = model.from_dict(row)
            _dict[row[model._key]].items.append(model._item_model.from_dict(row))
    return _dict


def parse_vehicle_dictionary(vehicle_dictionary_reader: DictReader) -> dict[str, Vehicle]:
    """
    Returns dictionary of vehicle ID: Vehicle.
    This file stores info about specific vehicle type and features.

         Documentation: https://www.ztm.poznan.pl/wp-content/uploads/2024/07/slownik-pojazdow-opis.pdf
    """
    return {row["vehicle"]: Vehicle.from_dict(row) for row in vehicle_dictionary_reader}


def parse_feed_info(z: ZipFile) -> FeedInfo:
    """
    Parse feed_info.txt.
    """
    with z.open(FeedInfo._gtfs_file) as f:
        reader = csv.DictReader(TextIOWrapper(f, encoding="utf-8-sig"))
        row = next(reader)
        return FeedInfo.from_dict(row)
