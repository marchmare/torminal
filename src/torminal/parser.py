import requests
import csv
from zipfile import ZipFile
from io import StringIO, TextIOWrapper
from typing import TypeVar, TypedDict
from .data import Vehicle, Stop, FeedInfo, Trip, Route, Shape, TripStops, GroupModel, Model

VEHICLE_DICTIONARY_URL = "https://www.ztm.poznan.pl/pl/dla-deweloperow/getGtfsRtFile/?file=vehicle_dictionary.csv"
GTFS_FILE_URL = "https://www.ztm.poznan.pl/pl/dla-deweloperow/getGTFSFile"
GTFS_FILE_NAME = "ZTMPoznanGTFS.zip"


def parse_vehicle_dictionary() -> dict[str, Vehicle]:
    """
    Request and parse vehicle_dictionary.csv to Vehicle objects. Returns dictionary of vehicle ID: Vehicle.
    This file stores info about specific vehicle type and features.

        Documentation: https://www.ztm.poznan.pl/wp-content/uploads/2024/07/slownik-pojazdow-opis.pdf
    """

    with requests.get(VEHICLE_DICTIONARY_URL) as response:
        response.raise_for_status()
        reader = csv.DictReader(StringIO(response.text))

    return {row["vehicle"]: Vehicle.from_dict(row) for row in reader}


def get_gtfs_zip() -> None:
    """
    Download GTFS zip archive with trips, stop times, stops, shapes, routes, feed_info, calendar dates, calendar and agency data.

        Documentation: https://www.ztm.poznan.pl/wp-content/uploads/2024/07/Specyfikacja-GTFS-04.02.2022.pdf
    """
    url = GTFS_FILE_URL

    headers = {
        "Accept": "application/octet-stream",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    with requests.get(url, headers=headers, stream=True) as response:
        response.raise_for_status()

        with open(GTFS_FILE_NAME, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)


M = TypeVar("M", bound=Model)
G = TypeVar("G", bound=GroupModel)


def parse_txt_as_dict(model: type[M]) -> dict[str, M]:
    """
    Parse a GTFS text file into a dictionary indexed by a unique key.

    Intended for files where the key column acts as a primary key and
    each key corresponds to a single record.
    """
    with ZipFile(GTFS_FILE_NAME) as z:
        with z.open(model._gtfs_file) as f:
            reader = csv.DictReader(TextIOWrapper(f, encoding="utf-8-sig"))
            return {row[model._key]: model.from_dict(row) for row in reader}


def parse_txt_as_dict_grouped(model: type[G]) -> dict[str, G]:
    """
    Parse a GTFS text file into a dictionary grouped by a key column.

    Intended for files where multiple records share the same key,
    representing a one-to-many relationship.
    """
    with ZipFile(GTFS_FILE_NAME) as z:
        with z.open(model._gtfs_file) as f:
            reader = csv.DictReader(TextIOWrapper(f, encoding="utf-8-sig"))
            _dict: dict[str, G] = {}

            for row in reader:
                if row[model._key] not in _dict:
                    _dict[row[model._key]] = model.from_dict(row)
                _dict[row[model._key]].items.append(model._item_model.from_dict(row))
    return _dict


def parse_feed_info() -> FeedInfo:
    """
    Parse feed_info.txt.
    This file stores info about feed publisher and related dates.
    """

    with ZipFile(GTFS_FILE_NAME) as z:
        with z.open("feed_info.txt") as f:
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


def load_lookup() -> GTFSLookup:
    return {
        "vehicles": parse_vehicle_dictionary(),
        "trips": parse_txt_as_dict(Trip),
        "trip_stops": parse_txt_as_dict_grouped(TripStops),
        "routes": parse_txt_as_dict(Route),
        "stops": parse_txt_as_dict(Stop),
        "shapes": parse_txt_as_dict_grouped(Shape),
    }
