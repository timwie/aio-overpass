"""Overpass QL helpers."""

import itertools

from shapely.geometry import Polygon


def poly_clause(shp: Polygon) -> str:
    """
    Poly region clause.

    This ``(poly:...)`` clause includes results that occur within the exterior of the given
    polygon. The input shape should be simplified, since a larger number of coordinates will
    slow down the query.

    References:
      - https://wiki.openstreetmap.org/wiki/Overpass_API/Language_Guide#Select_region_by_polygon
    """
    flattened_coords = itertools.chain.from_iterable(shp.exterior.coords[:-1])
    bounds = " ".join(map(str, flattened_coords))
    return f'(poly:"{bounds}")'


def one_of_filter(tag: str, *values: str) -> str:
    """
    Tag filter that requires elements to have a tag value that is in the list of the given ones.

    * returns no filter if ``values`` is empty
    * returns a simple ``[key="value1"]`` filter if ``values`` has one item
    * returns a regex filter ``[key~"^value1$|^value2$|..."]`` filter
      if ``values`` has multiple items

    References:
      - https://wiki.openstreetmap.org/wiki/Overpass_API/Language_Guide#Tag_request_clauses_(or_%22tag_filters%22)
    """
    if not values:
        return ""

    if len(values) == 1:
        return f'[{tag}="{values[0]}"]'

    regex = "|".join(f"^{v}$" for v in values)
    return f'[{tag}~"{regex}"]'
