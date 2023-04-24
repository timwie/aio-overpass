"""Overpass QL helpers."""

import itertools

from shapely.geometry import Polygon


def poly_filter(shp: Polygon) -> str:
    """
    Generate a ``poly:...`` clause.

    This clause includes results that occur within the exterior of the given polygon.
    The input shape should be simplified, since a larger number of coordinates will
    slow down the query.

    References:
        - https://wiki.openstreetmap.org/wiki/Overpass_API/Language_Guide#Select_region_by_polygon
    """
    flattened_coords = itertools.chain.from_iterable(shp.exterior.coords[:-1])
    bounds = " ".join(map(str, flattened_coords))
    return f'(poly:"{bounds}")'


def one_of_filter(tag: str, *values: str) -> str:
    """
    Generate a ``[tag~"^v1$|^v2$|..."]`` regex filter.

    This filter checks if the tag value is inside the list of the provided values.
    """
    if not values:
        return ""
    regex = "|".join(f"^{v}$" for v in values)
    return f'[{tag}~"{regex}"]'
