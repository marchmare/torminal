"""Python GTFS data models."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from torminal.gtfs.static import GTFSStaticFeed

from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from typing import Literal, TypeVar, Self, ClassVar, Generic, Any
from abc import ABC, abstractmethod
from bs4 import BeautifulSoup
from datetime import datetime, date, UTC
from shapely.geometry import LineString

import numpy as np
import polars as pl

from torminal.gtfs.time import (
    iso_to_dt,
    gtfs_date_to_dt,
    gtfs_time_to_dt,
    gtfs_dates_to_dt,
    gtfs_times_to_dt,
)
from torminal.gtfs.utils import enum_from_series, flag_to_bool


# TODO: consider changing how Model class is structured, so from_dict or from_df classes are not enforced?
class Model(ABC):
    _gtfs_file: ClassVar[str]
    _key: ClassVar[str]

    @classmethod
    @abstractmethod
    def from_dict(cls, row: dict[str, str]) -> Self:
        """Build models from csv DictReader."""
        ...

    @classmethod
    def from_df(cls, df: pl.DataFrame) -> Any:
        """Build models from a polars DataFrame with vectorized column conversion."""
        raise NotImplementedError


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

    @classmethod
    def from_df(cls, df: pl.DataFrame) -> dict[str, Self]:
        vehicle_id = df["vehicle"].str.strip_chars().cast(pl.Int32).to_list()
        vehicle_type = np.where(np.asarray(vehicle_id) <= 999, "tram", "bus")
        return {
            id: cls(
                id=id,
                vehicle_type=vehicle_type,
                floor_type=floor_type,
                has_ramp=has_ramp,
                has_ac=has_ac,
                has_bike_space=has_bike_space,
                has_va=has_va,
                has_ticket_machine=has_ticket_machine,
                has_driver_ticket_sales=has_driver_ticket_sales,
                has_usb_charger=has_usb_charger,
            )
            for (
                id,
                vehicle_type,
                floor_type,
                has_ramp,
                has_ac,
                has_bike_space,
                has_va,
                has_ticket_machine,
                has_driver_ticket_sales,
                has_usb_charger,
            ) in zip(
                df["vehicle"].to_list(),
                vehicle_type,
                enum_from_series(df["hf_lf_le"], FloorType),
                flag_to_bool(df["ramp"]),
                flag_to_bool(df["air_conditioner"]),
                flag_to_bool(df["place_for_transp_bicycles"]),
                flag_to_bool(df["voice_announcement_sys"]),
                flag_to_bool(df["ticket_machine"]),
                flag_to_bool(df["ticket_sales_by_the_driver"]),
                flag_to_bool(df["usb_charger"]),
            )
        }


@dataclass
class BollardMessage(Model):
    """Message displayed on a stop bollard."""

    start_date: datetime
    end_date: datetime
    link: str | None
    message: str

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> Self:  # type: ignore [override]
        soup = BeautifulSoup(row["content"], "html.parser")

        link_tag = soup.find("a")
        link = None
        if link_tag and hasattr(link_tag, "get"):
            link = link_tag.get("href")

        text = soup.get_text(" ", strip=True)

        return cls(
            start_date=iso_to_dt(row["startDate"]),
            end_date=iso_to_dt(row["endDate"]),
            link=str(link) if link else None,
            message=text,
        )


@dataclass
class BollardMessages(GroupModel[BollardMessage]):
    """List of messages displayed on stop bollards."""

    _item_model = BollardMessage

    items: list[BollardMessage] = field(default_factory=list)

    @classmethod
    def from_dict(cls, items: dict[str, dict[str, Any]]) -> Self:  # type: ignore [override]
        return cls(items=[BollardMessage.from_dict(item) for item in items])

    def get_current(self) -> BollardMessage | None:
        """Get the bollard info that applies in the most recent time period and includes today's date."""

        sorted_items = sorted(self.items, key=lambda item: item.start_date, reverse=True)
        for item in sorted_items:
            if item.start_date <= datetime.now(UTC) <= item.end_date:
                return item
        return None


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


class GTFSArchive:
    """Metadata of GTFS archive listed on https://www.ztm.poznan.pl/otwarte-dane/gtfsfiles/"""

    def __init__(self, filename: str, modified: str) -> None:
        self.filename: str = filename
        self.start_date: date = gtfs_date_to_dt(filename.split("_")[0])
        self.end_date: date = gtfs_date_to_dt(filename.split("_")[1].split(".")[0])
        self.modified: str = modified


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
    start_date: date
    end_date: date

    @classmethod
    def from_dict(cls, row: dict[str, str]) -> Self:
        return cls(
            publisher_name=row["feed_publisher_name"],
            publisher_url=row["feed_publisher_url"],
            language=row["feed_lang"],
            start_date=gtfs_date_to_dt(row["feed_start_date"]),
            end_date=gtfs_date_to_dt(row["feed_end_date"]),
        )


@dataclass
class ShapePoint(Model):
    """
    Single point of a trip shape, represented as geographic location.
    """

    _gtfs_file = "shapes.txt"
    _key = "shape_pt_sequence"

    sequence: int
    longitude: float
    latitude: float

    @classmethod
    def from_dict(cls, row: dict[str, str]) -> Self:
        return cls(
            sequence=int(row["shape_pt_sequence"]),
            longitude=float(row["shape_pt_lon"]),
            latitude=float(row["shape_pt_lat"]),
        )

    @classmethod
    def from_df(cls, df: pl.DataFrame) -> list[Self]:
        return [
            cls(sequence=sequence, longitude=longitude, latitude=latitude)
            for sequence, longitude, latitude in zip(
                df["shape_pt_sequence"].cast(pl.Int32).to_list(),
                df["shape_pt_lon"].cast(pl.Float64).to_list(),
                df["shape_pt_lat"].cast(pl.Float64).to_list(),
            )
        ]


@dataclass(frozen=True)
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

    @classmethod
    def from_df(cls, df: pl.DataFrame) -> dict[str, Self]:
        return {
            id: cls(
                id=id,
                agency_id=agency_id,
                short_name=short_name,
                long_name=long_name,
                description=description,
                type=type,
                color=color,
            )
            for id, agency_id, short_name, long_name, description, type, color in zip(
                df["route_id"].to_list(),
                df["agency_id"].to_list(),
                df["route_short_name"].to_list(),
                df["route_long_name"].to_list(),
                df["route_desc"].to_list(),
                enum_from_series(df["route_type"], VehicleType),
                df["route_color"].to_list(),
            )
        }


@dataclass(frozen=True)
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

    @classmethod
    def from_df(cls, df: pl.DataFrame) -> dict[str, Self]:
        return {
            id: cls(id, code, name, latitude, longitude, zone)
            for id, code, name, latitude, longitude, zone in zip(
                df["stop_id"].to_list(),
                df["stop_code"].to_list(),
                df["stop_name"].to_list(),
                df["stop_lat"].cast(pl.Float64).to_list(),
                df["stop_lon"].cast(pl.Float64).to_list(),
                enum_from_series(df["zone_id"], Zone),
            )
        }


@dataclass
class StopTime(Model):
    """Represents a single stop event within a GTFS trip."""

    _gtfs_file = "stop_times.txt"
    _key = "stop_sequence"

    sequence: int
    arrival_time: datetime
    departure_time: datetime
    stop_id: str
    pickup_type: DropoffPickupType
    drop_off_type: DropoffPickupType

    @classmethod
    def from_dict(cls, row: dict[str, str]) -> Self:
        return cls(
            sequence=int(row["stop_sequence"]),
            arrival_time=gtfs_time_to_dt(row["arrival_time"]),
            departure_time=gtfs_time_to_dt(row["departure_time"]),
            stop_id=row["stop_id"],
            pickup_type=DropoffPickupType(int(row["pickup_type"])),
            drop_off_type=DropoffPickupType(int(row["drop_off_type"])),
        )

    @classmethod
    def from_df(cls, df: pl.DataFrame) -> list[Self]:
        return [
            cls(
                sequence=sequence,
                arrival_time=arrival_time,
                departure_time=departure_time,
                stop_id=stop_id,
                pickup_type=pickup_type,
                drop_off_type=drop_off_type,
            )
            for sequence, arrival_time, departure_time, stop_id, pickup_type, drop_off_type in zip(
                df["stop_sequence"].cast(pl.Int32).to_list(),
                gtfs_times_to_dt(df["arrival_time"]),
                gtfs_times_to_dt(df["departure_time"]),
                df["stop_id"].to_list(),
                enum_from_series(df["pickup_type"], DropoffPickupType),
                enum_from_series(df["drop_off_type"], DropoffPickupType),
            )
        ]

    def stop(self, dataset: GTFSStaticFeed) -> Stop | str:
        """Get StopTimes's stop object from dataset, returns string code if not found"""
        return dataset.stops.get(self.stop_id, self.stop_code)


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
    stop_times: list[StopTime] = field(init=False)

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

    @classmethod
    def from_df(cls, df: pl.DataFrame) -> dict[str, Self]:
        return {
            trip_id: cls(
                trip_id,
                route_id,
                shape_id,
                service_id,
                headsign,
                direction,
                is_wheelchair_accessible,
                brigade,
            )
            for (
                trip_id,
                route_id,
                shape_id,
                service_id,
                headsign,
                direction,
                is_wheelchair_accessible,
                brigade,
            ) in zip(
                df["trip_id"].to_list(),
                df["route_id"].to_list(),
                df["shape_id"].to_list(),
                df["service_id"].to_list(),
                df["trip_headsign"].to_list(),
                enum_from_series(df["direction_id"], Direction),
                flag_to_bool(df["wheelchair_accessible"]),
                df["brigade"].cast(pl.Int32).to_list(),
            )
        }

    def route(self, dataset: GTFSStaticFeed) -> Route | str:
        """Get Trip's route object from dataset, returns string ID if not found"""
        return dataset.routes.get(self.route_id, self.route_id)

    def shape(self, dataset: GTFSStaticFeed) -> Shape | str:
        """Get Trip's shape object from dataset, returns string ID if not found"""
        return dataset.shapes.get(self.shape_id, self.shape_id)

    def service(self, dataset: GTFSStaticFeed) -> ServiceCalendar | str:
        """Get Trip's service calendar object from dataset, returns string ID if not found"""
        return dataset.service_calendars.get(self.service_id, self.service_id)


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
    start_date: date
    end_date: date

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
            start_date=gtfs_date_to_dt(row["start_date"]),
            end_date=gtfs_date_to_dt(row["end_date"]),
        )

    @classmethod
    def from_df(cls, df: pl.DataFrame) -> dict[str, Self]:
        return {
            id: cls(id, monday, tuesday, wednesday, thursday, friday, saturday, sunday, start_date, end_date)
            for (id, monday, tuesday, wednesday, thursday, friday, saturday, sunday, start_date, end_date) in zip(
                df["service_id"].to_list(),
                flag_to_bool(df["monday"]),
                flag_to_bool(df["tuesday"]),
                flag_to_bool(df["wednesday"]),
                flag_to_bool(df["thursday"]),
                flag_to_bool(df["friday"]),
                flag_to_bool(df["saturday"]),
                flag_to_bool(df["sunday"]),
                gtfs_dates_to_dt(df["start_date"]),
                gtfs_dates_to_dt(df["end_date"]),
            )
        }


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
    path: LineString = field(default_factory=LineString)

    @classmethod
    def from_dict(cls, row: dict[str, str]) -> Self:
        return cls(id=row["shape_id"])

    @classmethod
    def from_df(cls, df: pl.DataFrame) -> dict[str, Self]:
        points = ShapePoint.from_df(df)
        grouped = df.with_row_index("__idx").group_by("shape_id", maintain_order=True).agg(pl.col("__idx"))
        shapes: dict[str, Self] = {}
        for shape_id, indices in grouped.iter_rows():
            shapes[str(shape_id)] = cls(id=str(shape_id), items=[points[i] for i in indices])
        return shapes


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

    @classmethod
    def from_df(cls, df: pl.DataFrame) -> dict[str, Self]:
        items = StopTime.from_df(df)
        grouped = (
            df.with_row_index("__idx")
            .group_by("trip_id", maintain_order=True)
            .agg(pl.col("stop_headsign").first(), pl.col("__idx"))
        )
        trip_stops: dict[str, Self] = {}
        for trip_id, headsign, indices in grouped.iter_rows():
            trip_id = str(trip_id)
            trip_stops[trip_id] = cls(id=trip_id, headsign=str(headsign), items=[items[i] for i in indices])
        return trip_stops


### Custom TORminal-native data


class VehicleStatus(IntEnum):
    ON_TIME = 0
    """Going according to plan"""
    SLIGHTLY_DELAYED = 1
    """1-3 minutes of delay, but otherwise moving along typical path"""
    DELAYED = 2
    """Delay exceeding 3 minutes, but otherwise moving along typical path"""
    EARLY = 3
    """Negative delay exceeding tolerance, but otherwise moving along typical path"""
    DETOURED = 4
    """Vehicle outside of defined path"""
    STUCK = 5
    """Vehicle not moving for extended time"""
    AT_TERMINUS = 6
    """Vehicle is waiting to begin its trip"""
    NO_RT = 7
    """There's no RT data available for this trip"""
