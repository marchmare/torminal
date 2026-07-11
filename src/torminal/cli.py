from google.transit import gtfs_realtime_pb2
import requests
import csv
from zipfile import ZipFile
from io import StringIO, TextIOWrapper
from .data import Vehicle, Stop, FeedInfo, Trip, Route, Shape, ShapePoint, TripStops, StopTime, GroupLike
from typing import Any, Literal, TypeAlias, TypeVar

GTFS_ZIP = "ZTMPoznanGTFS.zip"
ZipTxt: TypeAlias = Literal[
    "trips", "stop_times", "stops", "shapes", "routes", "feed_info", "calendar_dates", "calendar", "agency"
]


def parse_vehicle_dictionary() -> dict[int, Vehicle]:
    """
    Request and parse vehicle_dictionary.csv to Vehicle objects. Returns dictionary of vehicle ID: Vehicle.
    This file stores info about specific vehicle type and features.

        Documentation: https://www.ztm.poznan.pl/wp-content/uploads/2024/07/slownik-pojazdow-opis.pdf
    """

    with requests.get(
        "https://www.ztm.poznan.pl/pl/dla-deweloperow/getGtfsRtFile/?file=vehicle_dictionary.csv"
    ) as response:
        response.raise_for_status()
        reader = csv.DictReader(StringIO(response.text))

    return {int(row["vehicle"]): Vehicle.from_dict(row) for row in reader}


def get_gtfs_zip() -> None:
    """
    Download GTFS zip archive with trips, stop times, stops, shapes, routes, feed_info, calendar dates, calendar and agency data.

        Documentation: https://www.ztm.poznan.pl/wp-content/uploads/2024/07/Specyfikacja-GTFS-04.02.2022.pdf
    """
    url = "https://www.ztm.poznan.pl/pl/dla-deweloperow/getGTFSFile"

    headers = {
        "Accept": "application/octet-stream",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    with requests.get(url, headers=headers, stream=True) as response:
        response.raise_for_status()

        with open(GTFS_ZIP, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)


def parse_txt_as_dict(key: str, source: ZipTxt) -> dict[Any, Any]:
    """
    Parse a GTFS text file into a dictionary indexed by a unique key.

    Intended for files where the key column acts as a primary key and
    each key corresponds to a single record.
    """

    source_mapping = {"stops": Stop, "trips": Trip, "routes": Route}
    if source not in source_mapping:
        raise RuntimeError(f"Source {source} not supported by `parse_txt_as_dict`")

    with ZipFile(GTFS_ZIP) as z:
        with z.open(source + ".txt") as f:
            reader = csv.DictReader(TextIOWrapper(f, encoding="utf-8-sig"))
            return {row[key]: source_mapping[source].from_dict(row) for row in reader}


T = TypeVar


def parse_txt_as_dict_grouped(key: str, source: ZipTxt) -> dict[Any, Any]:
    """
    Parse a GTFS text file into a dictionary grouped by a key column.

    Intended for files where multiple records share the same key,
    representing a one-to-many relationship.
    """
    source_mapping = {
        "shapes": (Shape, ShapePoint),
        "stop_times": (TripStops, StopTime),
    }
    if source not in source_mapping:
        raise RuntimeError(f"Source {source} not supported by `parse_txt_as_dict_grouped`")

    with ZipFile(GTFS_ZIP) as z:
        with z.open(source + ".txt") as f:
            reader = csv.DictReader(TextIOWrapper(f, encoding="utf-8-sig"))

            group_type, item_type = source_mapping[source]
            _dict: dict[str, GroupLike] = {}

            for row in reader:
                if row[key] not in _dict:
                    _dict[row[key]] = group_type.from_dict(row)
                _dict[row[key]].items.append(item_type.from_dict(row))
    return _dict


def parse_feed_info() -> FeedInfo:
    """
    Parse feed_info.txt.
    This file stores info about feed publisher and related dates.
    """

    with ZipFile(GTFS_ZIP) as z:
        with z.open("feed_info.txt") as f:
            reader = csv.DictReader(TextIOWrapper(f, encoding="utf-8-sig"))
            row = next(reader)
            return FeedInfo.from_dict(row)


def main() -> None:
    print("🚋 TORminal")

    # get lookup dictionaries
    vehicles = parse_vehicle_dictionary()
    trips = parse_txt_as_dict("trip_id", "trips")
    trip_stops = parse_txt_as_dict_grouped("trip_id", "stop_times")
    routes = parse_txt_as_dict("route_id", "routes")
    stops = parse_txt_as_dict("stop_id", "stops")
    shapes = parse_txt_as_dict_grouped("shape_id", "shapes")

    # summary
    print("Loaded data summary:")
    print(f"\t ⬩ vehicles: {len(vehicles)}")
    print(f"\t ⬩ trips: {len(trips)}")
    print(f"\t ⬩ trip stops: {len(trip_stops)} -> {sum([len(ts.items) for ts in trip_stops.values()])} events")
    print(f"\t ⬩ stops definitions: {len(stops)}")
    print(f"\t ⬩ trip routes definitions: {len(routes)}")
    print(f"\t ⬩ trip shapes definitions: {len(shapes)} -> {sum(len(p.items) for p in shapes.values())} points")
