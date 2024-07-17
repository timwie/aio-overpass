"""Basic definitions for (groups of) geospatial objects."""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, TypeAlias


__docformat__ = "google"
__all__ = (
    "GeoJsonDict",
    "SpatialDict",
    "Spatial",
)


GeoJsonDict: TypeAlias = dict[str, Any]
"""A dictionary representing a GeoJSON object."""


@dataclass(kw_only=True, slots=True)
class SpatialDict:
    """
    Mapping of spatial objects with the ``__geo_interface__`` property.

    Objects of this class have the ``__geo_interface__`` property following a protocol
    [proposed](https://gist.github.com/sgillies/2217756) by Sean Gillies, which can make
    it easier to use spatial data in other Python software. An example of this is the ``shape()``
    function that builds Shapely geometries from any object with the ``__geo_interface__`` property.

    Attributes:
        __geo_interface__: this is the proposed property that contains the spatial data
    """

    __geo_interface__: dict


class Spatial(ABC):
    """
    Base class for (groups of) geospatial objects.

    Classes that represent spatial features extend this class and implement the
    ``geojson`` property. Exporting objects in the GeoJSON format should make it possible
    to integrate them with other tools for visualization, or further analysis.
    The ability to re-import the exported GeoJSON structures as ``Spatial`` objects is not
    considered here.
    """

    __slots__ = ("__validated__",)  # we use that field in tests

    @property
    @abstractmethod
    def geojson(self) -> GeoJsonDict:
        """
        A mapping of this object, using the GeoJSON format.

        The coordinate reference system for all GeoJSON coordinates is ``CRS:84``,
        which means every coordinate is a tuple of longitude and latitude (in that order)
        on the WGS 84 ellipsoid. Note that this order is flipped for all Shapely geometries
        that represent OpenStreetMap elements (latitude first, then longitude).

        References:
            - https://osmdata.openstreetmap.de/info/projections.html
            - https://tools.ietf.org/html/rfc7946#section-4
        """
        raise NotImplementedError

    @property
    def geo_interfaces(self) -> Iterator[SpatialDict]:
        """A mapping of this object to ``SpatialDict``s that implement ``__geo_interface__``."""
        geojson = self.geojson
        match geojson["type"]:
            case "FeatureCollection":
                for feature in geojson["features"]:
                    yield SpatialDict(__geo_interface__=feature)
            case _:
                yield SpatialDict(__geo_interface__=geojson)
