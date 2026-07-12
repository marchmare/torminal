from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from typing import Literal, TypeVar, Self, ClassVar, Generic
from abc import ABC, abstractmethod


class Model(ABC):
    _gtfs_file: ClassVar[str]
    _key: ClassVar[str]

    @classmethod
    @abstractmethod
    def from_dict(cls, row: dict[str, str]) -> Self: ...


I = TypeVar("I", bound=Model)


class GroupModel(Model, Generic[I]):
    _gtfs_file: ClassVar[str]
    _key: ClassVar[str]
    _item_model: type[I]

    items: list[I]


### GTFS realtime data:


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

    _gtfs_file = "vehicle_dictionary.csv"
    _key = "vehicle"

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
    def from_dict(cls, row: dict[str, str]) -> Self:
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


### GTFS static data:
"""
                        ┌──────────────────┐                                                
                        │= trips.txt ======│                                                
                        │  trip_id (PK)    ├───────────────────────────────┐                
                ┌───────┤  route_id (FK)   ├───────┐                       │                
                │       │  shape_id (FK)   │       │                       │                
                │       └─────────┬────────┘       │                       │                
                │                 │                │                       │                
┌───────────────▼──┐    ┌─────────▼────────┐    ┌──▼───────────────┐    ┌──▼───────────────┐
│= shapes.txt =====│    │= stop_times.txt =│    │= routes.txt =====│    │= calendar.txt ===│
│                  │    │                  │    │                  │    │                  │
│  shape_id (PK)   │    │  trip_id (PK)    │    │  route_id (PK)   │    │  service_id (PK) │
│                  │    │  stop_id (FK)    │    │                  │    │                  │
└─────────┬────────┘    └─────────┬────────┘    └──────────────────┘    └──────────────────┘
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


class Direction(IntEnum):
    OUTBOUND = 0
    RETURN = 1


class VehicleType(IntEnum):
    TRAM_TROLLEY = 0
    """tram/trolleybus vehicle"""
    BUS = 3
    """bus vehicle"""


class Zone(StrEnum):
    A = "A"
    """Poznań city area."""
    B = "B"
    """Inner suburban area, including e.g. Czerwonak, Suchy Las, Swarzędz,
    Komorniki, Luboń, Rokietnica, Tarnowo Podgórne, Kórnik."""
    C = "C"
    """Outer suburban area, including e.g. Mosina, Murowana Goślina,
    Puszczykowo, Dopiewo, Kaźmierz, Pobiedziska."""
    D = "D"
    """Farthest ZTM service area, including e.g. Zaniemyśl and more distant
    localities outside the immediate Poznań metropolitan ring."""


class DropoffPickupType(IntEnum):
    """Informs if passengers can be picked up or dropped off on the stop."""

    POSSIBLE = 0
    IMPOSSIBLE = 1
    ON_REQUEST = 3


@dataclass
class FeedInfo:
    """
    Publisher data parsed from feed_info.txt.
    Generated from GTFS feed.
    Contains metadata about the feed publisher, version and validity period.
    """

    _gtfs_file = "feed_info.txt"

    publisher_name: str
    publisher_url: str
    language: str
    start_date: str
    end_date: str

    @classmethod
    def from_dict(cls, row: dict[str, str]) -> Self:
        return cls(
            publisher_name=row["feed_publisher_name"],
            publisher_url=row["feed_publisher_url"],
            language=row["feed_lang"],
            start_date=row["feed_start_date"],
            end_date=row["feed_end_date"],
        )


@dataclass
class Trip(Model):
    """
    Trip data parsed from trips.txt.
    Defines individual vehicle journeys associated with routes and services.
    A trip is a scheduled journey of a vehicle along a route and is identified by a unique `Trip ID`.
    `Trip ID` stores legend markers and trip variant info:

        1_11316657   ^   P,G:2:8   +
        ──────────       ───────   ─
        trip_id base     markers   main variant
    """

    _gtfs_file = "trips.txt"
    _key = "trip_id"

    id: str
    route_id: str
    shape_id: str
    service_id: str
    headsign: str
    direction: Direction
    is_wheelchair_accessible: bool
    brigade: int

    @classmethod
    def from_dict(cls, row: dict[str, str]) -> Self:
        return cls(
            id=row["trip_id"],
            route_id=row["route_id"],
            shape_id=row["shape_id"],
            service_id=row["service_id"],
            headsign=row["trip_headsign"],
            direction=Direction(int(row["direction_id"])),
            is_wheelchair_accessible=bool(int(row["wheelchair_accessible"])),
            brigade=int(row["brigade"]),
        )


@dataclass
class ShapePoint(Model):
    """
    Single point of a trip shape, represented as geographic location.
    """

    _gtfs_file = "shapes.txt"
    _key = "shape_pt_sequence"

    sequence: int
    latitude: float
    longitude: float

    @classmethod
    def from_dict(cls, row: dict[str, str]) -> Self:
        return cls(
            sequence=int(row["shape_pt_sequence"]),
            latitude=float(row["shape_pt_lat"]),
            longitude=float(row["shape_pt_lon"]),
        )


@dataclass
class Route(Model):
    """
    Route data parsed from routes.txt.
    Defines transport routes, their names, types and descriptions.
    """

    _gtfs_file = "routes.txt"
    _key = "route_id"

    id: str
    agency_id: str
    short_name: str
    long_name: str
    description: str
    type: VehicleType
    color: str

    @classmethod
    def from_dict(cls, row: dict[str, str]) -> Self:
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
class Stop(Model):
    """
    Stop data parsed from stops.txt.
    Contains definitions of stops, stations and their geographic locations.
    """

    _gtfs_file = "stops.txt"
    _key = "stop_id"

    id: str
    code: str
    name: str
    latitude: float
    longitude: float
    zone: Zone

    @classmethod
    def from_dict(cls, row: dict[str, str]) -> Self:
        return cls(
            id=row["stop_id"],
            code=row["stop_code"],
            name=row["stop_name"],
            latitude=float(row["stop_lat"]),
            longitude=float(row["stop_lon"]),
            zone=Zone(row["zone_id"]),
        )


@dataclass
class StopTime(Model):
    """Represents a single stop event within a GTFS trip."""

    _gtfs_file = "stop_times.txt"
    _key = "stop_sequence"

    sequence: int
    arrival_time: str  # custom GTFS time format
    departure_time: str  # custom GTFS time format
    stop_id: str
    pickup_type: DropoffPickupType
    drop_off_type: DropoffPickupType

    @classmethod
    def from_dict(cls, row: dict[str, str]) -> Self:
        return cls(
            sequence=int(row["stop_sequence"]),
            arrival_time=row["arrival_time"],
            departure_time=row["departure_time"],
            stop_id=row["stop_id"],
            pickup_type=DropoffPickupType(int(row["pickup_type"])),
            drop_off_type=DropoffPickupType(int(row["drop_off_type"])),
        )


@dataclass
class ServiceCalendar(Model):
    """
    Service calendar data parsed from calendar.txt.
    Defines service calendars and the dates on which trips operate.
    """

    _gtfs_file = "calendar.txt"
    _key = "service_id"

    id: str
    monday: bool
    tuesday: bool
    wednesday: bool
    thursday: bool
    friday: bool
    saturday: bool
    sunday: bool
    start_date: str
    end_date: str

    @classmethod
    def from_dict(cls, row: dict[str, str]) -> Self:
        return cls(
            id=row["service_id"],
            monday=bool(int(row["monday"])),
            tuesday=bool(int(row["tuesday"])),
            wednesday=bool(int(row["wednesday"])),
            thursday=bool(int(row["thursday"])),
            friday=bool(int(row["friday"])),
            saturday=bool(int(row["saturday"])),
            sunday=bool(int(row["sunday"])),
            start_date=row["start_date"],
            end_date=row["end_date"],
        )


@dataclass
class Shape(GroupModel[ShapePoint]):
    """
    Shape data parsed from shape.txt.
    Contains ordered geographic points describing the path followed by trips.
    """

    _gtfs_file = "shapes.txt"
    _key = "shape_id"
    _item_model = ShapePoint

    id: str
    items: list[ShapePoint] = field(default_factory=list)

    @classmethod
    def from_dict(cls, row: dict[str, str]) -> Self:
        return cls(id=row["shape_id"])


@dataclass
class TripStops(GroupModel[StopTime]):
    """
    Stop times data parsed from stop_times.txt.
    Contains ordered geographic points describing the path followed by trips.
    """

    _gtfs_file = "stop_times.txt"
    _key = "trip_id"
    _item_model = StopTime

    id: str
    headsign: str
    items: list[StopTime] = field(default_factory=list)

    @classmethod
    def from_dict(cls, row: dict[str, str]) -> Self:
        return cls(id=row["trip_id"], headsign=row["stop_headsign"])
