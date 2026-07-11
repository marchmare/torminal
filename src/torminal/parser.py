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
    print("\t ⬩ downloading and parsing vehicle_dictionary.csv")
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

    print(f"\t ⬩ downloading {GTFS_FILE_NAME}")
    with requests.get(url, headers=headers, stream=True) as response:
        response.raise_for_status()

        with open(GTFS_FILE_NAME, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)


M = TypeVar("M", bound=Model)
G = TypeVar("G", bound=GroupModel)


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
    feed_info: FeedInfo


def load_lookup() -> GTFSLookup:
    print("Loading GTFS data...")
    get_gtfs_zip()

    with ZipFile(GTFS_FILE_NAME) as z:
        return {
            "vehicles": parse_vehicle_dictionary(),
            "trips": parse_txt_as_dict(Trip, z),
            "trip_stops": parse_txt_as_dict_grouped(TripStops, z),
            "routes": parse_txt_as_dict(Route, z),
            "stops": parse_txt_as_dict(Stop, z),
            "shapes": parse_txt_as_dict_grouped(Shape, z),
            "feed_info": parse_feed_info(z),
        }


def print_summary(lookup: GTFSLookup) -> None:
    print("Loaded data summary:")
    print(f"\t ⬩ vehicles: {len(lookup['vehicles'])}")
    print(f"\t ⬩ trips: {len(lookup['trips'])}")
    print(
        f"\t ⬩ trip stops: {len(lookup['trip_stops'])} -> "
        f"{sum(len(ts.items) for ts in lookup['trip_stops'].values())} events"
    )
    print(f"\t ⬩ stops definitions: {len(lookup['stops'])}")
    print(f"\t ⬩ trip routes definitions: {len(lookup['routes'])}")
    print(
        f"\t ⬩ trip shapes definitions: {len(lookup['shapes'])} -> "
        f"{sum(len(p.items) for p in lookup['shapes'].values())} points"
    )
    print(lookup["feed_info"])
