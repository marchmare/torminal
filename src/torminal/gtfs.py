"""GTFS parsers to TORminal data models and dictionaries."""

import csv
from zipfile import ZipFile
from io import TextIOWrapper
from typing import TypeVar, TypedDict
from csv import DictReader
from google.transit.gtfs_realtime_pb2 import TripUpdate, FeedEntity
from google.protobuf.internal.containers import RepeatedCompositeFieldContainer

from .data import Vehicle, Stop, FeedInfo, Trip, Route, Shape, ServiceCalendar, TripStops, GroupModel, Model
from .requests import open_gtfs_zip, open_vehicle_dictionary

VEHICLE_DICTIONARY_URL = "https://www.ztm.poznan.pl/pl/dla-deweloperow/getGtfsRtFile/?file=vehicle_dictionary.csv"
GTFS_FILE_URL = "https://www.ztm.poznan.pl/pl/dla-deweloperow/getGTFSFile"
GTFS_FILE_NAME = "ZTMPoznanGTFS.zip"

M = TypeVar("M", bound=Model)
G = TypeVar("G", bound=GroupModel)


### GTFS realtime data:


def parse_gtfs_rt_data(feed: RepeatedCompositeFieldContainer[FeedEntity]) -> dict[str, dict[str, TripUpdate]]:
    """
    Returns dictionary of trip ID: gtfs_realtime_pb2.TripUpdate.

        Documentation: https://gtfs.org/documentation/realtime/reference/#message-tripupdate
    """

    return {e.trip_update.trip.trip_id: e.trip_update for e in feed}


### GTFS static data:


def parse_txt_as_dict(model: type[M], z: ZipFile) -> dict[str, M]:
    """
    Parse a GTFS text file into a dictionary indexed by a unique key.

    Intended for files where the key column acts as a primary key and
    each key corresponds to a single record.
    """
    print(f"\t ⬩ parsing {model._gtfs_file}")

    with z.open(model._gtfs_file) as f:
        reader = csv.DictReader(TextIOWrapper(f, encoding="utf-8-sig"))
        return {row[model._key]: model.from_dict(row) for row in reader}


def parse_txt_as_dict_grouped(model: type[G], z: ZipFile) -> dict[str, G]:
    """
    Parse a GTFS text file into a dictionary grouped by a key column.

    Intended for files where multiple records share the same key,
    representing a one-to-many relationship.
    """
    print(f"\t ⬩ parsing {model._gtfs_file}")

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
    This file stores info about feed publisher and related dates.
    """
    print(f"\t ⬩ parsing {FeedInfo._gtfs_file}")

    with z.open(FeedInfo._gtfs_file) as f:
        reader = csv.DictReader(TextIOWrapper(f, encoding="utf-8-sig"))
        row = next(reader)
        return FeedInfo.from_dict(row)


class GTFSLookup(TypedDict):
    vehicles: dict[str, Vehicle]
    trips: dict[str, Trip]
    trip_stops: dict[str, TripStops]
    routes: dict[str, Route]
    stops: dict[str, Stop]
    shapes: dict[str, Shape]
    service_calendars: dict[str, ServiceCalendar]
    feed_info: FeedInfo


def load_lookup() -> GTFSLookup:
    print("Loading GTFS data...")

    with open_vehicle_dictionary() as vd:
        vehicle_dictionary = parse_vehicle_dictionary(vd)

    with open_gtfs_zip() as z:
        return {
            "vehicles": vehicle_dictionary,
            "trips": parse_txt_as_dict(Trip, z),
            "trip_stops": parse_txt_as_dict_grouped(TripStops, z),
            "routes": parse_txt_as_dict(Route, z),
            "stops": parse_txt_as_dict(Stop, z),
            "shapes": parse_txt_as_dict_grouped(Shape, z),
            "service_calendars": parse_txt_as_dict(ServiceCalendar, z),
            "feed_info": parse_feed_info(z),
        }


def print_summary(lookup: GTFSLookup) -> None:
    trip_stop_events = sum(len(ts.items) for ts in lookup["trip_stops"].values())
    shape_points = sum(len(shape.items) for shape in lookup["shapes"].values())

    print(f"""Loaded data summary:
    ⬩ vehicles: {len(lookup["vehicles"])}
    ⬩ trips: {len(lookup["trips"])}
    ⬩ trip stops: {len(lookup["trip_stops"])} -> {trip_stop_events} events
    ⬩ stops definitions: {len(lookup["stops"])}
    ⬩ trip routes definitions: {len(lookup["routes"])}
    ⬩ trip shapes definitions: {len(lookup["shapes"])} -> {shape_points} points
    ⬩ service calendars: {len(lookup["service_calendars"])}
    {lookup["feed_info"]}
    """)
