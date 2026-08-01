from __future__ import annotations

from datetime import datetime
from enum import Enum, IntEnum
from typing import TYPE_CHECKING, Any
import numpy as np
from pandas import Series

if TYPE_CHECKING:
    from torminal.gtfs.data import ServiceCalendar

from torminal.gtfs.time import weekday_names


class ArrivalTime:
    """Class calculating planned and live arrival times"""

    time: datetime
    """Exact time of arrival"""
    eta: int
    """Time left to arrival in minutes"""
    delay: int
    """Delay in seconds (can be negative, if vehicle passed a stop early)"""

    def __init__(self, arrival_time: datetime, delay: int = 0) -> None:

        self.time = arrival_time
        self.eta = self.estimate_arrival(arrival_time)
        self.delay = delay

    def __repr__(self) -> str:
        fields = (f"time={self.time!r}", f"eta={self.eta!r}", f"delay={self.delay!r}")
        return f"{self.__class__.__name__}({', '.join(fields)})"

    @staticmethod
    def estimate_arrival(arrival_time: datetime) -> int:
        """Calculate how many minutes are left till vehicle departs."""
        delta = arrival_time - datetime.now()
        return int(delta.total_seconds() // 60)


def resolve_service_calendar(dataset) -> ServiceCalendar | None:
    """Get service calendar object for today's weekday."""
    current_weekday = datetime.today().weekday()

    for service in dataset.service_calendars.values():
        if getattr(service, weekday_names[current_weekday]):
            return service
    return None


def enum_from_series(series: Any, enum_type: type[Enum]) -> list[Enum]:
    """Map a column of unique enum string values to enum members, vectorized."""

    values = np.asarray(series, dtype=str)
    if issubclass(enum_type, IntEnum):  # convert to int values if IntEnum
        values = values.astype(int)  # otherwise keep StrEnum

    # cache enum construction per distinct value for faster lookup
    mapping: dict[Any, Enum] = {value: enum_type(value) for value in np.unique(values)}
    return [mapping[value] for value in values]


def flag_to_bool(series: Any) -> Series:
    """
    Convert a Series of "0"/"1" (or int) GTFS flag values into booleans.
    Maps 0 -> False, nonzero -> True.
    """
    return series.astype(int).astype(bool)
