"""
Module handling processing of vehicle and stop position data.

Disclaimer for using shapely with pyproj:
(x, y) = (lon, lat)
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from torminal.gtfs.data import ShapePoint, Shape

from shapely.geometry import Point, Polygon
from pyproj import Transformer

# transformers
proj_to2180 = Transformer.from_crs("EPSG:4326", "EPSG:2180", always_xy=True)
"""Convert to local metric PL-2000 Polish CRS (metric, flat grid)"""
proj_to4326 = Transformer.from_crs("EPSG:2180", "EPSG:4326", always_xy=True)
"""Convert to WGS-84 global GPS standard CRS (spherical, lat/lon)"""


def gps_point(longitude: float, latitude: float) -> Point:
    """Convert longitude and latitude to Point, transformed to PL-2000"""

    return Point(*proj_to2180.transform(longitude, latitude))


def calculate_points_distance(point1: Point, point2: Point) -> float:
    """Calculate distance between two points (in PL-2000 meters)."""

    return point1.distance(point2)


def shape_to_polygon(shape_points: list[ShapePoint]) -> Polygon:
    """Create Polygon out of ShapePoints defined for a Shape (already in PL-2000)."""

    ordered_list = sorted(shape_points, key=lambda item: item.sequence)
    return Polygon([item.point for item in ordered_list])


def check_point_on_shape(point: Point, shape: Shape | Polygon, radius: int = 50) -> bool:
    """Check if point is in close proximity of the polygon defined by Shape."""

    if isinstance(shape, Shape):
        polygon = shape_to_polygon(shape.items)
    else:
        polygon = shape

    buffered_polygon = polygon.buffer(radius)
    return buffered_polygon.contains(point)


def calculate_velocity(
    entry1: tuple[int, int, Point],
    entry2: tuple[int, int, Point],
) -> float:
    """
    Calculate velocity based on two position history entries
    defined by tuples of (timestamp, current_stop, position).
    Returns velocity in km/h.
    """

    distance = entry1[2].distance(entry2[2])
    d_time = entry2[0] - entry1[0]

    if d_time == 0:
        return 0.0

    return (distance / d_time) * 3.6


def calculate_mean_velocity(position_history: list[tuple[int, int | None, Point | None]]) -> float | None:
    """Calculate mean velocity."""

    valid = [(timestamp, position) for timestamp, _, position in position_history if position is not None]
    if len(valid) < 2:
        return None

    velocities = [calculate_velocity(entry1, entry2) for (entry1, entry2) in zip(valid, valid[1:])]
    return sum(velocities) / len(velocities)
