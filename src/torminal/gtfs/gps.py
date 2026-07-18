"""
Module handling processing of vehicle and stop position data.

Disclaimer for using shapely with pyproj:
(x, y) = (lon, lat)
"""

from shapely.geometry import Point, Polygon
from shapely.ops import transform
from pyproj import Transformer
from datetime import datetime

from torminal.gtfs.data import Position, ShapePoint, Shape

# transformers
proj_to2180 = Transformer.from_crs("EPSG:4326", "EPSG:2180", always_xy=True)
"""Convert to local metric PL-2000 Polish CRS (metric, flat grid)"""
proj_to4326 = Transformer.from_crs("EPSG:2180", "EPSG:4326", always_xy=True)
"""Convert to WGS-84 global GPS standard CRS (spherical, lat/lon)"""


def _point(point: Position) -> Point:
    """Convert Position to Point, transformed to PL-2000"""
    return Point(*proj_to2180.transform(point.longitude, point.latitude))


def calculate_points_distance(point1: Position, point2: Position) -> float:
    """Calculate distance between two points"""

    p1 = _point(point1)
    p2 = _point(point2)

    return p1.distance(p2)


def shape_to_polygon(shape_points: list[ShapePoint]) -> Polygon:
    """Create Polygon out of ShapePoints defined for a Shape"""

    ordered_list = sorted(shape_points, key=lambda item: item.sequence)

    polygon = Polygon([(item.longitude, item.latitude) for item in ordered_list])
    return transform(proj_to2180.transform, polygon)


def check_point_on_shape(point: Position, shape: Shape | Polygon, radius: int = 50) -> bool:
    """Check if point is in close proximity of the polygon defined by Shape"""

    p = _point(point)
    if isinstance(shape, Shape):
        polygon = shape_to_polygon(shape.items)
    else:
        polygon = shape

    buffered_polygon = polygon.buffer(radius)
    return buffered_polygon.contains(p)


def calculate_velocity(
    entry1: tuple[int, int, Position],
    entry2: tuple[int, int, Position],
) -> float:
    """
    Calculate velocity based on two position history entries
    defined by tuples of (timestamp, current_stop, position).
    Returns velocity in km/h.
    """

    point1 = _point(entry1[2])
    point2 = _point(entry2[2])

    distance = point1.distance(point2)
    d_time = entry2[0] - entry1[0]

    if d_time == 0:
        return 0.0

    return (distance / d_time) * 3.6


def calculate_mean_velocity(position_history: list[tuple[int, int | None, Position | None]]) -> float | None:
    """Calculate mean velocity"""

    valid = [(timestamp, position) for timestamp, _, position in position_history if position is not None]
    if len(valid) < 2:
        return None

    velocities = [calculate_velocity(entry1, entry2) for (entry1, entry2) in zip(valid, valid[1:])]
    return sum(velocities) / len(velocities)
