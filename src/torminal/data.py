from dataclasses import dataclass, field
from enum import IntEnum
from typing import Literal, Protocol

### GTFS-Realtime related data -------------------------


class FloorType(IntEnum):
    HIGH_FLOOR = 0
    """high-floor vehicle"""
    LOW_FLOOR = 1
    """low-floor vehicle"""
    LOW_ENTRY = 2
    """partially low-floor/low-entry vehicle"""


@dataclass
class Vehicle:
    """
    Vehicle data parsed from vehicle_dictionary.csv
    Used by GTFS-Realtime.
    """

    id: str
    vehicle_type: Literal["tram", "bus"]
    floor_type: FloorType
    has_ramp: bool
    has_ac: bool
    has_bike_space: bool
    has_va: bool
    has_ticket_machine: bool
    has_driver_ticket_sales: bool
    has_usb_charger: bool

    @classmethod
    def from_dict(cls, row: dict[str, str]) -> "Vehicle":
        return cls(
            id=row["vehicle"],
            vehicle_type="tram" if int(row["vehicle"]) <= 999 else "bus",
            floor_type=FloorType(int(row["hf_lf_le"])),
            has_ramp=bool(int(row["ramp"])),
            has_ac=bool(int(row["air_conditioner"])),
            has_bike_space=bool(int(row["place_for_transp_bicycles"])),
            has_va=bool(int(row["voice_announcement_sys"])),
            has_ticket_machine=bool(int(row["ticket_machine"])),
            has_driver_ticket_sales=bool(int(row["ticket_sales_by_the_driver"])),
            has_usb_charger=bool(int(row["usb_charger"])),
        )


### Static GTFS related data -------------------------
"""
                        ┌──────────────────┐                        
                        │= trips.txt ======│                        
                        │  trip_id (PK)    │                        
                ┌───────┼  route_id (FK)   ┼───────┐                
                │       │  shape_id (FK)   │       │                
                │       └─────────┬────────┘       │                
                │                 │                │                
┌───────────────▼──┐    ┌─────────▼────────┐    ┌──▼───────────────┐
│= shapes.txt =====│    │= stop_times.txt =│    │= routes.txt =====│
│                  │    │                  │    │                  │
│  shape_id (PK)   │    │  trip_id (PK)    │    │  route_id (PK)   │
│                  │    │  stop_id (FK)    │    │                  │
└─────────┬────────┘    └─────────┬────────┘    └──────────────────┘
          │                       │                                 
┌─────────▼────────┐    ┌─────────▼────────┐                        
│= shape_point ====│    │= stop_time ======│                        
│                  │    │                  │                        
│  shape_id (PK)   │    │  trip_id (PK)    │                        
│                  │    │  stop_id (FK)    │                        
└──────────────────┘    └─────────┬────────┘                        
                                  │                                 
                        ┌─────────▼────────┐                        
                        │= stops.txt ======│                        
                        │                  │                        
                        │  stop_id (PK)    │                        
                        │                  │                        
                        └──────────────────┘                        
"""


class SequencedItem(Protocol):
    sequence: int


class GroupLike(Protocol):
    items: list[SequencedItem]


class Direction(IntEnum):
    OUTBOUND = 0
    RETURN = 1


@dataclass
class Trip:
    """
    Trip data parsed from trips.txt.
    Defines individual vehicle journeys associated with routes and services.
    A trip is a scheduled journey of a vehicle along a route and is identified by a unique `Trip ID`.
    `Trip ID` stores legend markers and trip variant info:

        1_11316657   ^   P,G:2:8   +
        ──────────       ───────   ─
        trip_id base     markers   main variant
    """

    id: str
    route_id: str
    shape_id: str
    headsign: str
    direction: Direction
    is_wheelchair_accessible: bool
    brigade: int

    @classmethod
    def from_dict(cls, row: dict[str, str]) -> "Trip":
        return (
            cls(
                id=row["trip_id"],
                route_id=row["route_id"],
                shape_id=row["shape_id"],
                headsign=row["trip_headsign"],
                direction=Direction(int(row["direction_id"])),
                is_wheelchair_accessible=bool(int(row["wheelchair_accessible"])),
                brigade=int(row["brigade"]),
            ),
        )


@dataclass
class ShapePoint:
    """
    Single point of a trip shape, represented as geographic location.
    """

    sequence: int
    latitude: float
    longitude: float

    @classmethod
    def from_dict(cls, row: dict[str, str]) -> "ShapePoint":
        return cls(
            sequence=int(row["shape_pt_sequence"]),
            latitude=float(row["shape_pt_lat"]),
            longitude=float(row["shape_pt_lon"]),
        )


@dataclass
class Shape:
    """
    Shape data parsed from shape.txt.
    Contains ordered geographic points describing the path followed by trips.
    """

    id: str
    items: list[ShapePoint] = field(default_factory=list)

    @classmethod
    def from_dict(cls, row: dict[str, str]) -> "Shape":
        return cls(id=row["shape_id"])


class VehicleType(IntEnum):
    TRAM_TROLLEY = 0
    """tram/trolleybus vehicle"""
    BUS = 3
    """bus vehicle"""


@dataclass
class Route:
    """
    Route data parsed from routes.txt.
    Defines transport routes, their names, types and descriptions.
    """

    id: str
    agency_id: str
    short_name: str
    long_name: str
    description: str
    type: VehicleType
    color: str

    @classmethod
    def from_dict(cls, row: dict[str, str]) -> "Stop":
        return cls(
            id=row["route_id"],
            agency_id=row["agency_id"],
            short_name=row["route_short_name"],
            long_name=row["route_long_name"],
            description=row["route_desc"],
            type=VehicleType(int(row["route_type"])),
            color=row["route_color"],
        )


@dataclass
class Stop:
    """
    Stop data parsed from stops.txt.
    Contains definitions of stops, stations and their geographic locations.
    """

    id: str
    code: str
    name: str
    latitude: float
    longitude: float
    zone: Literal["A", "B", "C", "D"]

    @classmethod
    def from_dict(cls, row: dict[str, str]) -> "Stop":
        return cls(
            id=row["stop_id"],
            code=row["stop_code"],
            name=row["stop_name"],
            latitude=float(row["stop_lat"]),
            longitude=float(row["stop_lon"]),
            zone=row["zone_id"],
        )


class DropoffPickupType(IntEnum):
    """Informs if passengers can be picked up or dropped off on the stop."""

    POSSIBLE = 0
    IMPOSSIBLE = 1
    ON_REQUEST = 3


@dataclass
class StopTime:
    """Represents a single stop event within a GTFS trip."""

    sequence: int
    arrival_time: str  # custom GTFS time format
    departure_time: str  # custom GTFS time format
    stop_id: str
    pickup_type: DropoffPickupType
    drop_off_type: DropoffPickupType

    @classmethod
    def from_dict(cls, row: dict[str, str]) -> "StopTime":
        return cls(
            sequence=int(row["stop_sequence"]),
            arrival_time=row["arrival_time"],
            departure_time=row["departure_time"],
            stop_id=row["stop_id"],
            pickup_type=DropoffPickupType(int(row["pickup_type"])),
            drop_off_type=DropoffPickupType(int(row["drop_off_type"])),
        )


@dataclass
class TripStops:
    """
    Stop times data parsed from stop_times.txt.
    Contains ordered geographic points describing the path followed by trips.
    """

    id: str
    headsign: str
    items: list[StopTime] = field(default_factory=list)

    @classmethod
    def from_dict(cls, row: dict[str, str]) -> "TripStops":
        return cls(id=row["trip_id"], headsign=row["stop_headsign"])


@dataclass
class FeedInfo:
    """
    Publisher data parsed from feed_info.txt.
    Generated from GTFS feed.
    Contains metadata about the feed publisher, version and validity period.
    """

    publisher_name: str
    publisher_url: str
    language: str
    start_date: str
    end_date: str

    @classmethod
    def from_dict(cls, row: dict[str, str]) -> "Stop":
        return cls(
            publisher_name=row["feed_publisher_name"],
            publisher_url=row["feed_publisher_url"],
            language=row["feed_lang"],
            start_date=row["feed_start_date"],
            end_date=row["feed_end_date"],
        )
