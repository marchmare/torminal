import csv
from typing import Callable, TypeVar
from dataclasses import dataclass
from csv import DictReader
from zipfile import ZipFile
from io import TextIOWrapper

from torminal.requests import open_gtfs_zip, open_vehicle_dictionary
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
        self.total: int = 9

    def _emit_progress(self, message: str) -> None:
        """Execute callback function with ProgressEvent"""
        self.callback(ProgressEvent(current=self.current, total=self.total, message=message))

    def _step(self) -> None:
        """Update current counter by 1"""
        self.current += 1

    def load(self) -> GTFSStaticFeed:
        """Load GTFS static data."""
        self._emit_progress("Loading vehicle_dictionary.csv")
        with open_vehicle_dictionary() as vd:
            vehicles = parse_vehicle_dictionary(vd)
        self._step()

        self._emit_progress("Loading GTFS archive")
        with open_gtfs_zip() as z:
            self._step()

            self._emit_progress("Loading trips.txt")
            trips = parse_txt_as_dict(Trip, z)
            self._step()

            self._emit_progress("Loading trip_stops.txt")
            trip_stops = parse_txt_as_dict_grouped(TripStops, z)
            self._step()

            self._emit_progress("Loading routes.txt")
            routes = parse_txt_as_dict(Route, z)
            self._step()

            self._emit_progress("Loading stops.txt")
            stops = parse_txt_as_dict(Stop, z)
            self._step()

            self._emit_progress("Loading shapes.txt")
            shapes = parse_txt_as_dict_grouped(Shape, z)
            self._step()

            self._emit_progress("Loading service.txt")
            service_calendars = parse_txt_as_dict(ServiceCalendar, z)
            self._step()

            self._emit_progress("Loading feed_info.txt")
            feed_info = parse_feed_info(z)
            self._step()

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
            self._emit_progress("Finished")
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
