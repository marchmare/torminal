"""Module for handling GTFS realtime data"""

from dataclasses import dataclass
from google.transit.gtfs_realtime_pb2 import TripUpdate, VehiclePosition
from torminal.requests import fetch_protobuf, GTFS_RT_TRIP_UPDATES_URL, GTFS_RT_VEHICLE_POSITIONS_URL


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


def fetch_gtfs_rt_feed() -> GTFSRealTimeFeed:
    """Request GTFS realtime feed and return GTFSRealTimeFeed object for it."""
    _gtfs_rt_trip_updates = fetch_protobuf(GTFS_RT_TRIP_UPDATES_URL)
    _gtfs_rt_vehicle_positions = fetch_protobuf(GTFS_RT_VEHICLE_POSITIONS_URL)

    return GTFSRealTimeFeed(
        trip_updates={e.trip_update.trip.trip_id: e.trip_update for e in _gtfs_rt_trip_updates},
        vehicle_positions={e.vehicle.trip.trip_id: e.vehicle for e in _gtfs_rt_vehicle_positions},
    )
