"""Module for accessing GTFS files published by ZTM and handling other HTTP requests."""

import requests
import csv
from typing import Any, Generator
from google.protobuf.internal.containers import RepeatedCompositeFieldContainer
from google.transit import gtfs_realtime_pb2
from google.transit.gtfs_realtime_pb2 import FeedEntity
from pathlib import Path
from zipfile import ZipFile
from datetime import datetime
from io import TextIOWrapper
from contextlib import contextmanager

from .data import FeedInfo
from .time_utils import convert_feed_info_date

GTFS_RT_TRIP_UPDATES_URL = "https://www.ztm.poznan.pl/pl/dla-deweloperow/getGtfsRtFile?file=trip_updates.pb"
VEHICLE_DICTIONARY_URL = "https://www.ztm.poznan.pl/pl/dla-deweloperow/getGtfsRtFile/?file=vehicle_dictionary.csv"
VEHICLE_DICTIONARY_NAME = "vehicle_dictionary.csv"
GTFS_FILE_URL = "https://www.ztm.poznan.pl/pl/dla-deweloperow/getGTFSFile"
GTFS_FILE_NAME = "ZTMPoznanGTFS.zip"

HEADERS = {
    "Accept": "application/octet-stream",
    "Content-Type": "application/x-www-form-urlencoded",
}


def download_file(filename: str, url: str) -> None:
    """Download file helper function."""

    print(f"\t ⬩ downloading {filename}")
    response = requests.get(url, headers=HEADERS, stream=True)
    response.raise_for_status()

    with open(filename, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)


def fetch_gtfs_rt_feed() -> RepeatedCompositeFieldContainer[FeedEntity]:
    """Fetch most recent GTFS realtime feed with trip updates."""

    feed = gtfs_realtime_pb2.FeedMessage()
    response = requests.get(GTFS_RT_TRIP_UPDATES_URL)
    response.raise_for_status()
    feed.ParseFromString(response.content)
    return feed.entity


def gtfs_needs_update() -> bool:
    """Verify if GTFS zip exists and if it's up to date."""

    gtfs_path = Path(GTFS_FILE_NAME)

    if not gtfs_path.exists():
        return True

    with ZipFile(GTFS_FILE_NAME) as z:
        with z.open(FeedInfo._gtfs_file) as f:
            reader = csv.DictReader(TextIOWrapper(f, encoding="utf-8-sig"))
            row = next(reader)
            feed_info = FeedInfo.from_dict(row)

    return convert_feed_info_date(feed_info.end_date) < datetime.today()


@contextmanager
def open_gtfs_zip() -> Generator[ZipFile, Any, None]:
    """
    Download and read GTFS zip archive with trips, stop times, stops, shapes, routes, feed_info, calendar dates, calendar and agency data.

        Documentation: https://www.ztm.poznan.pl/wp-content/uploads/2024/07/Specyfikacja-GTFS-04.02.2022.pdf
    """
    if gtfs_needs_update():
        download_file(GTFS_FILE_NAME, GTFS_FILE_URL)

    with ZipFile(GTFS_FILE_NAME) as z:
        yield z


@contextmanager
def open_vehicle_dictionary() -> Generator[csv.DictReader, Any, None]:
    """
    Download and read vehicle_dictionary.csv with vehicle properties.

        Documentation: https://www.ztm.poznan.pl/wp-content/uploads/2024/07/slownik-pojazdow-opis.pdf
    """
    download_file(VEHICLE_DICTIONARY_NAME, VEHICLE_DICTIONARY_URL)

    with open(VEHICLE_DICTIONARY_NAME, "r") as file:
        yield csv.DictReader(file)
