"""Module for accessing GTFS files published by ZTM and handling other HTTP requests."""

import requests
import csv
import json
from typing import Any, Generator, Optional
from google.protobuf.internal.containers import RepeatedCompositeFieldContainer
from google.transit import gtfs_realtime_pb2
from google.transit.gtfs_realtime_pb2 import FeedEntity
from pathlib import Path
from zipfile import ZipFile
from contextlib import contextmanager
from time import time
from platformdirs import user_config_dir, user_cache_dir
from bs4 import BeautifulSoup
from datetime import datetime

from torminal.gtfs.data import GTFSArchive

GTFS_RT_TRIP_UPDATES_URL = "https://www.ztm.poznan.pl/pl/dla-deweloperow/getGtfsRtFile?file=trip_updates.pb"
GTFS_RT_VEHICLE_POSITIONS_URL = "https://www.ztm.poznan.pl/pl/dla-deweloperow/getGtfsRtFile?file=vehicle_positions.pb"
VEHICLE_DICTIONARY_URL = "https://www.ztm.poznan.pl/pl/dla-deweloperow/getGtfsRtFile/?file=vehicle_dictionary.csv"
VEHICLE_DICTIONARY_NAME = "vehicle_dictionary.csv"
GTFS_FILE_URL = "https://www.ztm.poznan.pl/pl/dla-deweloperow/getGTFSFile"
GTFS_SITE_URL = "https://www.ztm.poznan.pl/otwarte-dane/gtfsfiles/"
GTFS_FILE_NAME = "ZTMPoznanGTFS.zip"
PEKA_VM_URL = "https://www.peka.poznan.pl/vm/method.vm"

CACHE_DIR = Path(user_cache_dir("TORminal", "marchmare"))
CONFIG_DIR = Path(user_config_dir("TORminal", "marchmare"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "Accept": "application/octet-stream",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
}


def download_file(output_file: str, url: str, params: Optional[str] = "") -> None:
    """Download file helper function."""
    _url = f"{url}{params}"
    response = requests.get(_url, headers=HEADERS, stream=True)
    response.raise_for_status()
    with open(f"{CACHE_DIR}/{output_file}", "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)


def fetch_protobuf(url: str) -> RepeatedCompositeFieldContainer[FeedEntity]:
    """Fetch GTFS Protobuf feed from specified URL."""

    feed = gtfs_realtime_pb2.FeedMessage()
    response = requests.get(url)
    response.raise_for_status()
    feed.ParseFromString(response.content)
    return feed.entity


def fetch_form_post(url: str, method: str, params: dict[str, Any]) -> Any:
    """Fetch response from URL using form POST with JSON blobs inside parameters."""

    _params = json.dumps(params)
    payload = {"method": method, "p0": _params}

    response = requests.post(
        url,
        params={"ts": int(time() * 1000)},
        data=payload,
        headers=HEADERS,
    )
    response.raise_for_status()
    return response.json()


def get_gtfs_archive_list() -> list[GTFSArchive]:
    """
    Scrape list of available GTFS archives from https://www.ztm.poznan.pl/otwarte-dane/gtfsfiles/
    The most recent archives are on top.
    """

    response = requests.get(GTFS_SITE_URL)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    archives: list[GTFSArchive] = []

    for table_container in soup.select("div.table-responsive"):
        for row in table_container.select("tbody tr"):
            cells = row.find_all("td")

            archives.append(
                GTFSArchive(
                    cells[0].get_text(strip=True),
                    cells[2].get_text(strip=True),
                )
            )
    return archives


def resolve_current_gtfs_archive() -> GTFSArchive | None:
    """
    Resolve most recent and currently applicable GTFS archive.
    ZTM publishes GTFS archives ahead of time and with overlapping dates.
    """
    archives = get_gtfs_archive_list()
    today = datetime.today().date()

    for archive in archives:
        if archive.start_date <= today <= archive.end_date:
            return archive
    return None


@contextmanager
def open_gtfs_zip() -> Generator[ZipFile, Any, None]:
    """
    Download and read GTFS zip archive with trips, stop times, stops, shapes, routes, feed_info, calendar dates, calendar and agency data.

        Documentation: https://www.ztm.poznan.pl/wp-content/uploads/2024/07/Specyfikacja-GTFS-04.02.2022.pdf
    """
    current_archive = resolve_current_gtfs_archive()
    if not current_archive:
        raise RuntimeError("No available GTFS archive.")

    # Schedule of ZTM publications of the GTFS archive are still mystery to me,
    # sometimes it uses the most recent one and sometimes the one that came before (since the newest one is usually published ahead of time)
    #
    # Leaving those two lines in case they're need to be switched,
    # potential way to workaround this: download and load two datasets, swap if one doesn't yield any results,
    # ideally with some early check during loading
    #
    download_file(output_file=GTFS_FILE_NAME, url=GTFS_FILE_URL, params=f"/?file={current_archive.filename}")
    # download_file(output_file=GTFS_FILE_NAME, url=GTFS_FILE_URL)

    with ZipFile(f"{CACHE_DIR}/{GTFS_FILE_NAME}") as z:
        yield z


@contextmanager
def open_vehicle_dictionary() -> Generator[csv.DictReader, Any, None]:
    """
    Download and read vehicle_dictionary.csv with vehicle properties.

        Documentation: https://www.ztm.poznan.pl/wp-content/uploads/2024/07/slownik-pojazdow-opis.pdf
    """
    download_file(output_file=VEHICLE_DICTIONARY_NAME, url=VEHICLE_DICTIONARY_URL)

    with open(f"{CACHE_DIR}/{VEHICLE_DICTIONARY_NAME}", "r") as file:
        yield csv.DictReader(file)
