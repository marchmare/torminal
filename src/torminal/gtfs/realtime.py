"""Module for handling GTFS realtime data"""

from dataclasses import dataclass
from google.transit.gtfs_realtime_pb2 import TripUpdate, VehiclePosition

from torminal.requests import (
    fetch_protobuf,
    fetch_form_post,
    GTFS_RT_TRIP_UPDATES_URL,
    GTFS_RT_VEHICLE_POSITIONS_URL,
    PEKA_VM_URL,
)
from torminal.gtfs.data import Stop


@dataclass
class GTFSRealTimeFeed:
    """
    Storage class for realtime feeds fetched and parsed from Protobuf files.

    Documentation:
        * trip updates: https://gtfs.org/documentation/realtime/reference/#message-tripupdate
        * vehicle positions: https://gtfs.org/documentation/realtime/reference/#message-vehicleposition
    """

    trip_updates: dict[str, TripUpdate]
    vehicle_positions: dict[str, VehiclePosition]


@dataclass
class PEKARealTimeFeed:
    """
    Storage class for realtime feeds fetched and parsed from PEKA virtual monitor (https://www.peka.poznan.pl/vm/).
    """

    bollard: dict[str, dict]
    times: dict[str, dict]
    message: dict[str, dict]


def fetch_gtfs_rt_feed() -> GTFSRealTimeFeed:
    """Request GTFS realtime feed and return GTFSRealTimeFeed object for it."""
    _gtfs_rt_trip_updates = fetch_protobuf(GTFS_RT_TRIP_UPDATES_URL)
    _gtfs_rt_vehicle_positions = fetch_protobuf(GTFS_RT_VEHICLE_POSITIONS_URL)

    return GTFSRealTimeFeed(
        trip_updates={e.trip_update.trip.trip_id: e.trip_update for e in _gtfs_rt_trip_updates},
        vehicle_positions={e.vehicle.trip.trip_id: e.vehicle for e in _gtfs_rt_vehicle_positions},
    )


def fetch_peka_vm_feed(stop: Stop | None) -> PEKARealTimeFeed | None:
    """Request feed from PEKA virtual monitor for specified stop."""
    if not stop:
        return None

    _times = fetch_form_post(PEKA_VM_URL, method="getTimes", params={"symbol": stop.code})
    """Returns list of upcoming departures from the stop"""

    _bollard_msg = fetch_form_post(PEKA_VM_URL, method="findMessagesForBollard", params={"symbol": stop.code})
    """Returns message currently displayed on a bollard from specified stop."""

    # _bollards_by_stop_point = fetch_form_post(
    #     PEKA_VM_URL, method="getBollardsByStopPoint", params={"symbol": stop.name}
    # )
    # """Returns all stops with the same name and lists all routes that belong to each"""

    return PEKARealTimeFeed(
        bollard=_times["success"]["bollard"], times=_times["success"]["times"], message=_bollard_msg["success"]
    )
