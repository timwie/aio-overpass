"""Typed result set members."""

from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any, Optional, Union, cast

from aio_overpass import Query

import shapely.geometry
import shapely.ops
from shapely.geometry import (
    GeometryCollection,
    LinearRing,
    LineString,
    MultiPolygon,
    Point,
    Polygon,
)
from shapely.geometry.base import BaseGeometry, BaseMultipartGeometry


__docformat__ = "google"
__all__ = (
    "GeoJsonDict",
    "OverpassDict",
    "Bbox",
    "Spatial",
    "Element",
    "Node",
    "Way",
    "Relation",
    "AreaWay",
    "AreaRelation",
    "Relationship",
    "Metadata",
    "collect_elements",
)

GeoJsonDict = dict[str, Any]
"""
A dictionary representing a GeoJSON object.
"""

OverpassDict = dict[str, Any]
"""
A dictionary representing a JSON object returned by the Overpass API.
"""

Bbox = tuple[float, float, float, float]
"""
The bounding box of a spatial object.

This tuple can be understood as any of
    - ``(s, w, n, e)``
    - ``(minlat, minlon, maxlat, maxlon)``
    - ``(minx, miny, maxx, maxy)``
"""


class Spatial(ABC):
    """
    Base class for (groups of) geospatial objects.

    Classes that represent spatial features extend this class and implement the
    ``geojson`` property. Exporting objects in the GeoJSON format should make it possible
    to integrate them with other tools for visualization, or further analysis.

    Objects of this class have the ``__geo_interface__`` property to follow a protocol proposed
    by Sean Gillies, which can make it easier to use spatial data in other Python software
    (https://gist.github.com/sgillies/2217756). An example of this is the ``shape()`` function
    that builds Shapely geometries from any object with the ``__geo_interface__`` property.

    The ability to re-import the exported GeoJSON structures as ``Spatial`` objects is not
    considered here. If you want import/export functionality for ``Spatial`` objects,
    you might want to use something like ``pickle`` (https://docs.python.org/3/library/pickle.html).
    """

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
    def __geo_interface__(self) -> GeoJsonDict:
        """See ``geojson``."""
        return self.geojson


@dataclass(repr=False)
class Metadata:
    """
    Metadata concerning the most recent edit of an OSM element.

    Attributes:
        version: The version number of the element
        timestamp: Timestamp (ISO 8601) of the most recent change of this element
        changeset: The changeset in which the element was most recently changed
        user_name: Name of the user that made the most recent change to the element
        user_id: ID of the user that made the most recent change to the element
    """

    version: int
    timestamp: str
    changeset: int
    user_name: str
    user_id: int


@dataclass(repr=False, eq=False)
class Element(Spatial):
    """
    Elements are the basic components of OpenStreetMap's data.

    A query's result set is made up of these elements.

    Objects of this class do not necessarily describe OSM elements in their entirety.
    The degrees of detail are decided by the ``out`` statements used in an Overpass query:
    using ``out ids`` f.e. would only include an element's ID, but not its tags, geometry, etc.

    Element geometries have coordinates in the EPSG:4326 coordinate reference system,
    meaning that the coordinates are (latitude, longitude) tuples on the WGS 84 reference ellipsoid.
    The geometries are Shapely objects, where the x/y coordinates refer to lat/lon.
    Since Shapely works on the Cartesian plane, not all operations are useful: distances between
    Shapely objects are Euclidean distances for instance - not geodetic distances.

    Tags provide the semantics of elements. There are *classifying* tags, where for a certain key
    there is a limited number of agreed upon values: the ``highway`` tag f.e. is used to identify
    any kind of road, street or path, and to classify its importance within the road network.
    Deviating values are perceived as erroneous. Other tags are *describing*, where any value
    is acceptable for a certain key: the ``name`` tag is a prominent example for this.

    Objects of this class are not meant to represent "derived elements" of the Overpass API,
    that can have an entirely different data structure compared to traditional elements.
    An example of this is the structure produced by ``out count``, but also special statements like
    ``make`` and ``convert``.

    Attributes:
        id: A number that uniquely identifies an element of a certain type
            (nodes, ways and relations each have their own ID space)
        tags: A list of key-value pairs that describe the element, or ``None`` if the element's
              tags not included in the query's result set.
        bounds: The bounding box of this element, or ``None`` when not using ``out bbox``.
                The ``bounds`` property of Shapely geometries can be used as a replacement.
        center: The center of ``bounds``. If you need a coordinate that is inside the element's
                geometry, consider Shapely's ``representative_point()`` and ``centroid``.
        meta: Metadata of this element, or ``None`` when not using ``out meta``
        relations: All relations that are **also in the query's result set**, and that
                   **are known** to contain this element as a member.

    References:
        - https://wiki.openstreetmap.org/wiki/Elements
        - https://wiki.openstreetmap.org/wiki/Map_features
        - https://wiki.openstreetmap.org/wiki/Overpass_API/Overpass_QL#out
    """

    id: int
    tags: Optional[OverpassDict]
    bounds: Optional[Bbox]
    center: Optional[Point]
    meta: Optional[Metadata]
    relations: list["Relationship"]

    def tag(self, key: str, default: Any = None) -> Any:
        """
        Get the tag value for the given key.

        Returns ``default`` if there is no ``key`` tag.

        References:
            - https://wiki.openstreetmap.org/wiki/Tags
        """
        if not self.tags:
            return default
        return self.tags.get(key, default)

    @property
    def type(self) -> str:
        """The element's type: "node", "way", or "relation"."""
        if isinstance(self, Node):
            return "node"
        if isinstance(self, Way):
            return "way"
        if isinstance(self, Relation):
            return "relation"
        raise ValueError()

    @property
    def link(self) -> str:
        """This element on openstreetmap.org."""
        return f"https://www.openstreetmap.org/{self.type}/{self.id}"

    @property
    def geojson(self) -> GeoJsonDict:
        """
        A mapping of this object, using the GeoJSON format.

        Objects are mapped as the following:
         - ``Node`` -> ``Feature`` with optional ``Point`` geometry
         - ``Way`` -> ``Feature`` with optional ``LineString`` geometry
         - ``AreaWay`` -> ``Feature`` with optional ``Polygon`` geometry
         - ``AreaRelation`` -> ``Feature`` with optional ``Polygon`` or ``MultiPolygon`` geometry
         - ``Relation`` -> ``FeatureCollection`` (nested ``Relations`` are mapped to unlocated
           ``Features``)

        ``Feature`` properties contain all the following keys if they are present for the element:
        ``id``, ``type``, ``role``, ``tags``, ``nodes``, ``bounds``, ``center``, ``timestamp``,
        ``version``, ``changeset``, ``user``, ``uid``.
        The JSON object in ``properties`` is therefore very similar to the original JSON object
        returned by Overpass, skipping only ``geometry``, ``lat`` and ``lon``.

        Additionally, features inside ``FeatureCollections`` receive the special ``__rel__``
        property. Its value is an object containing all properties of the relation the collection
        represents. This works around the fact that ``FeatureCollections`` have no ``properties``
        member. The benefit is that you can take relation tags into consideration when styling
        and rendering their members on a map (f.e. with Leaflet). The downside is that these
        properties are duplicated for every feature.
        """
        if type(self) != Relation:
            return _geojson_feature(self)

        return {
            "type": "FeatureCollection",
            "features": [_geojson_feature(relship) for relship in self.members],
        }

    @property
    def _geometry(self) -> BaseGeometry:
        return getattr(self, "geometry", GeometryCollection())

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.id})"


def _geojson_properties(obj: Union[Element, "Relationship"]) -> GeoJsonDict:
    elem = obj if isinstance(obj, Element) else obj.member

    properties = {
        "id": elem.id,
        "type": elem.type,
        "tags": elem.tags,
        "bounds": elem.bounds,
        "center": elem.center.coords[0] if elem.center else None,
        "timestamp": elem.meta.timestamp if elem.meta else None,
        "version": elem.meta.version if elem.meta else None,
        "changeset": elem.meta.changeset if elem.meta else None,
        "user": elem.meta.user_name if elem.meta else None,
        "uid": elem.meta.user_id if elem.meta else None,
        "nodes": getattr(elem, "nodes", None),
    }

    properties = {k: v for k, v in properties.items() if v is not None}

    if isinstance(obj, Relationship):
        properties["role"] = obj.role or ""
        properties["__rel__"] = _geojson_properties(obj.relation)

    return properties


def _geojson_geometry(obj: Union[Element, "Relationship"]) -> Optional[GeoJsonDict]:
    elem = obj if isinstance(obj, Element) else obj.member

    geom = elem._geometry
    if not geom:
        return None

    # Flip coordinates for GeoJSON compliance.
    geom = shapely.ops.transform(lambda lat, lon: (lon, lat), geom)

    return shapely.geometry.mapping(geom)


def _geojson_bbox(obj: Union[Element, "Relationship"]) -> Optional[Bbox]:
    elem = obj if isinstance(obj, Element) else obj.member

    bounds = elem._geometry.bounds
    if bounds:
        (minlat, minlon, maxlat, maxlon) = bounds
        return minlon, minlat, maxlon, maxlat

    return None


def _geojson_feature(obj: Union[Element, "Relationship"]) -> GeoJsonDict:
    feature = {
        "type": "Feature",
        "geometry": _geojson_geometry(obj),
        "properties": _geojson_properties(obj),
    }

    bbox = _geojson_bbox(obj)
    if bbox:
        feature["bbox"] = bbox  # type: ignore

    return feature


@dataclass(repr=False, eq=False)
class Node(Element):
    """
    A point in space, at a specific coordinate.

    Nodes are used to define standalone point features (e.g. a bench),
    or to define the shape or "path" of a way.

    Attributes:
        geometry: A Point or ``None`` if the coordinate is not included in the query's result set.

    References:
        - https://wiki.openstreetmap.org/wiki/Node
    """

    geometry: Optional[Point]


@dataclass(repr=False, eq=False)
class Way(Element):
    """
    A way is an ordered list of nodes.

    An open way is a way whose first node is not its last node (e.g. a railway line).
    A closed way is a way whose first node is also its last node, and may be interpreted either
    as a closed polyline (e.g. a roundabout), an area (e.g. a patch of grass), or both
    (e.g. a roundabout surrounding a grassy area).

    For ways that enclose an area, refer to the ``AreaWay`` class.

    Attributes:
        node_ids: The IDs of the nodes that make up this way, or ``None`` if they are not included
                  in the query's result set.
        geometry: A Linestring if the way is open, a LinearRing if the way is closed,
                  a Polygon if the way is closed and its tags indicate that it represents an area,
                  or ``None`` if the geometry is not included in the query's result set.

    References:
        - https://wiki.openstreetmap.org/wiki/Way
    """

    node_ids: Optional[list[int]]
    geometry: Union[LineString, LinearRing, None]


@dataclass(repr=False, eq=False)
class Relation(Element):
    """
    A relation is a group of nodes and ways that have a logical or geographic relationship.

    This relationship is described through its tags.

    For relations that describe an area, refer to the ``AreaRelation`` class.

    Attributes:
        members: Ordered member elements of this relation, with an optional role

    References:
        - https://wiki.openstreetmap.org/wiki/Relation
    """

    members: list["Relationship"]

    def __iter__(self) -> Iterator[tuple[Optional[str], Element]]:
        for relship in self.members:
            yield relship.role, relship.member


@dataclass(repr=False, eq=False)
class AreaWay(Way):
    """
    An area whose outline is defined by a closed way.

    Unless this element was produced by an ``area`` query, this is not necessarily an area
    as defined by the Overpass API, since the criteria to decide which elements represent
    an area may differ.

    Attributes:
        area_id: An ID specific to the Overpass API, which is only set when explicitly querying
                 areas. Otherwise, you cannot be sure that this object is also considered an area
                 by Overpass. You can derive this ID yourself by adding ``2_400_000_000`` onto
                 the element ID, but must consider that there is no Overpass area with that ID.
        geometry: The polygon enclosed by the way.

    References:
        - https://wiki.openstreetmap.org/wiki/Area
        - https://wiki.openstreetmap.org/wiki/Overpass_API/Areas
    """

    area_id: Optional[int]
    geometry: Optional[Polygon]


@dataclass(repr=False, eq=False)
class AreaRelation(Relation):
    """
    An area whose geometry is defined by a relation.

    Areas defined by relations may have boundaries made up of several unclosed ways.

    Relations of ``type=multipolygon`` may have boundaries ("outer" role) and holes ("inner" role)
    made up of several unclosed ways.

    Tags describing the multipolygon always go on the relation. The inner and outer ways are tagged
    if they describe something in their own right. For example,
     - a multipolygon relation may be tagged as landuse=forest if it outlines a forest,
     - its outer ways may be tagged as barrier=fence if the forest is fenced,
     - and its inner ways may be tagged as natural=water if there is a lake within the forest
       boundaries.

    Unless this element was produced by an ``area`` query, this is not necessarily an area
    as defined by the Overpass API, since the criteria to decide which elements represent
    an area may differ.

    Attributes:
        area_id: An ID specific to the Overpass API, which is only set when explicitly querying
                 areas. Otherwise, you cannot be sure that this object is also considered an area
                 by Overpass. You can derive this ID yourself by adding ``3_600_000_000`` onto the
                 element ID, but must consider that there is no Overpass area with that ID.
        geometry: The complex polygons whose boundaries and holes are made up of the ways
                  inside the relation. Members that are not ways, or are not part of any polygon
                  boundary, are not part of the result geometry. ``None`` if the geometry of the
                  relation members is not included in the query's result set.

    References:
        - https://wiki.openstreetmap.org/wiki/Area
        - https://wiki.openstreetmap.org/wiki/Relation:multipolygon
        - https://wiki.openstreetmap.org/wiki/Relation:boundary
        - https://wiki.openstreetmap.org/wiki/Overpass_API/Areas
    """

    area_id: Optional[int]
    geometry: Union[Polygon, MultiPolygon, None]


@dataclass(repr=False)
class Relationship(Spatial):
    """
    The relationship of an element that is part of a relation, with an optional role.

    Attributes:
        member:     any element
        relation:   a relation that the member is a part of
        role:       describes the function of the member in the context of the relation

    References:
        - https://wiki.openstreetmap.org/wiki/Relation#Roles
    """

    member: Element
    relation: Relation
    role: Optional[str]

    @property
    def geojson(self) -> GeoJsonDict:
        """
        A mapping of ``member``.

        This is ``member.geojson``, with the added properties ``role`` and ``__rel__``.
        """
        return _geojson_feature(self)

    def __repr__(self) -> str:
        role = f" as '{self.role}'" if self.role else " "
        return f"{type(self).__name__}({self.member}{role} in {self.relation})"


_KNOWN_ELEMENTS = {"node", "way", "relation", "area"}


_ElementKey = tuple[str, int]
"""Elements are uniquely identified by the tuple (type, id)."""

_MemberKey = tuple[_ElementKey, str]
"""Relation members are identified by their element key and role."""


class _ElementCollector:
    def __init__(self) -> None:
        self.list: list[Element] = []
        self.typed_dict: dict[_ElementKey, Element] = {}
        self.untyped_dict: dict[_ElementKey, OverpassDict] = defaultdict(dict)
        self.member_dict: dict[int, list[_MemberKey]] = defaultdict(list)


def collect_elements(query: Query) -> list[Element]:
    """
    Produce typed elements from the result set of a query.

    This function collects elements that are of type "node", "way", "relation", or "area".
    Derived elements with other types - f.e. produced by ``make`` and ``convert`` statements
    or when using ``out count`` - are ignored. An exception is made for areas, which are so
    closely derived from ways and relations that it makes sense to represent them as such.
    If you need to work with other derived elements, you should not use this function.

    Element data is "conflated", which means that if elements appear more than once in a
    result set, their data is merged. This is useful f.e. when querying tags for relation members:
    using ``rel(...); out tags;`` will only print tags for relation itself, not its members.
    For those you will have to recurse down from the relation, which means members will show
    up twice in the result set: once untagged as a member of the relation, and once tagged at
    the top level. This function will have these two occurrences point to the same, single object.

    The order of elements is retained, but duplicate elements are reduced to a single entry.
    The order of relation members is retained.

    Args:
        query: a finished query

    Returns:
        a list of distinct, typed elements produced by the result set

    Raises:
        ValueError: If the input query is unfinished/has no result set.
        KeyError: The only times there should be missing keys is when either using ``out noids``,
                  or when building derived elements that are missing common keys.
    """
    if not query.done:
        msg = "query has no result set"
        raise ValueError(msg)

    collector = _ElementCollector()
    _collect_untyped(query, collector)
    _collect_typed(collector)
    _collect_relationships(collector)
    return collector.list


def _collect_untyped(query: Query, collector: _ElementCollector) -> None:
    if not query.result_set:
        raise AssertionError

    # Here we populate 'untyped_dict' with both top level elements, and
    # relation members, while conflating their data if they appear as both.
    # We also populate 'member_dict'.
    for elem_dict in query.result_set["elements"]:
        if elem_dict.get("type") not in _KNOWN_ELEMENTS:
            continue

        key: _ElementKey = (elem_dict["type"], elem_dict["id"])
        collector.untyped_dict[key].update(elem_dict)

        if elem_dict["type"] != "relation":
            continue

        for mem in elem_dict["members"]:
            key = (mem["type"], mem["ref"])
            collector.untyped_dict[key].update(mem)
            collector.member_dict[elem_dict["id"]].append((key, mem.get("role")))


def _collect_typed(collector: _ElementCollector) -> None:
    for elem_key, elem_dict in collector.untyped_dict.items():
        (elem_type, elem_id) = elem_key

        args = dict(
            id=elem_id,
            tags=elem_dict.get("tags"),
            bounds=tuple(elem_dict["bounds"].values()) if "bounds" in elem_dict else None,
            center=Point(elem_dict["center"].values()) if "center" in elem_dict else None,
            meta=Metadata(
                timestamp=elem_dict["timestamp"],
                version=elem_dict["version"],
                changeset=elem_dict["changeset"],
                user_name=elem_dict["user"],
                user_id=elem_dict["uid"],
            )
            if "timestamp" in elem_dict
            else None,
            relations=[],  # add later
        )

        cls: type[Element]

        if elem_type == "node":
            cls = Node

        elif elem_type == "way":
            cls = Way
            args["node_ids"] = elem_dict.get("nodes")
            if _is_area_element(elem_dict):
                cls = AreaWay
                args["area_id"] = elem_id % _AREA_REL_ID_OFFSET

        elif elem_type == "relation":
            cls = Relation
            args["members"] = []  # add later
            if _is_area_element(elem_dict):
                cls = AreaRelation
                args["area_id"] = elem_id % _AREA_REL_ID_OFFSET

        elif elem_id > _AREA_REL_ID_OFFSET:
            cls = AreaRelation
            args["area_id"] = elem_id % _AREA_REL_ID_OFFSET
            args["members"] = []  # add later

        else:
            cls = AreaWay
            args["area_id"] = elem_id % _AREA_WAY_ID_OFFSET

        if cls is not Relation:
            args["geometry"] = _geometry(elem_dict)

        elem = cls(**args)
        collector.list.append(elem)
        collector.typed_dict[elem_key] = elem


def _collect_relationships(collector: _ElementCollector) -> None:
    for rel_id, mem_roles in collector.member_dict.items():
        rel = cast(Relation, collector.typed_dict[("relation", rel_id)])

        for mem_key, mem_role in mem_roles:
            mem = collector.typed_dict[mem_key]
            relship = Relationship(member=mem, relation=rel, role=mem_role or None)
            mem.relations.append(relship)
            rel.members.append(relship)


# e.g. area with id 3_600_051_477 correlates with relation 51_477
_AREA_REL_ID_OFFSET = 3_600_000_000
_AREA_WAY_ID_OFFSET = 2_400_000_000


def _geometry(raw_elem: OverpassDict) -> Optional[BaseGeometry]:
    """
    Construct the geometry a given OSM element makes up.

    Args:
        raw_elem: an element from a query's result set

    Returns:
        - None if there is no geometry available for this element.
        - Point when given a node.
        - LineString when given an open way.
        - LinearRing when given a closed way, that supposedly is *not* an area.
        - Polygon when given a closed way, that supposedly is an area.
        - (Multi-)Polygons containing given a (multipolygon) relation.
          Relation members that are not ways, or are not part of any polygon boundary, are
          not part of the result geometry.

    Raises:
        ValueError: if element is not of type 'node', 'way', 'relation', or 'area'
    """
    if raw_elem.get("type") not in _KNOWN_ELEMENTS:
        msg = "expected element of type 'node', 'way', 'relation', or 'area'"
        raise ValueError(msg)

    if raw_elem["type"] == "node":
        lat, lon = raw_elem.get("lat"), raw_elem.get("lon")
        if lat and lon:
            return Point(lat, lon)

    if raw_elem["type"] == "way":
        ls = _line(raw_elem)
        if ls and ls.is_ring and _is_area_element(raw_elem):
            return Polygon(ls)
        return ls

    if _is_area_element(raw_elem):
        outers = (
            ls
            for ls in (
                _line(mem) for mem in raw_elem.get("members", ()) if mem.get("role") == "outer"
            )
            if ls
        )
        inners = (
            ls
            for ls in (
                _line(mem) for mem in raw_elem.get("members", ()) if mem.get("role") == "inner"
            )
            if ls
        )

        shells = [ls for ls in _flatten(shapely.ops.linemerge(outers)) if ls.is_closed]
        holes = [ls for ls in _flatten(shapely.ops.linemerge(inners)) if ls.is_closed]

        polys = [
            Polygon(shell=shell, holes=[hole for hole in holes if shell.contains(hole)])
            for shell in shells
        ]

        if len(polys) == 1:
            return polys[0]

        return MultiPolygon(polys)

    return None


def _line(way: OverpassDict) -> Union[LineString, LinearRing, None]:
    """Returns the geometry of a way in the result set."""
    if "geometry" not in way or len(way["geometry"]) < 2:
        return None
    is_ring = way["geometry"][0] == way["geometry"][-1]
    cls = LinearRing if is_ring else LineString
    return cls((c["lat"], c["lon"]) for c in way["geometry"])


def _flatten(obj: BaseGeometry) -> Iterable[BaseGeometry]:
    """Recursively flattens multipart geometries."""
    if isinstance(obj, BaseMultipartGeometry):
        return (nested for contained in obj.geoms for nested in _flatten(contained))
    return (obj,)


def _is_area_element(el: OverpassDict) -> bool:
    """
    Decide if ``el`` likely represents an area, and should be viewed as a (multi-)polygon.

    Args:
        el: a way or relation from a query's result set

    Returns:
        ``False`` if the input is not a relation or closed way.
        ``False``, unless there are tags which indicate that the way represents an area.

    References:
        - https://wiki.openstreetmap.org/wiki/Overpass_API/Areas
        - https://github.com/drolbr/Overpass-API/blob/master/src/rules/areas.osm3s
          (from 2018-04-09)
        - https://wiki.openstreetmap.org/wiki/Overpass_turbo/Polygon_Features
        - https://github.com/tyrasd/osm-polygon-features/blob/master/polygon-features.json
          (from 2016-11-03)
    """
    # Check if the element is explicitly an area
    if el["type"] == "area":
        return True

    # Check if a given way is open
    if el["type"] == "way" and ("geometry" not in el or el["geometry"][0] != el["geometry"][-1]):
        return False

    # Assume not an area if there are no tags available
    if "tags" not in el:
        return False

    tags = el["tags"]

    # Check if the element is explicitly tagged as not area
    if tags.get("area") == "no":
        return False

    # Check if there is a tag where any value other than 'no' suggests area
    # (note: Overpass may require the "name" tag as well)
    if any(tags.get(name, "no") != "no" for name in _AREA_TAG_NAMES):
        return True

    # Check if there are tag values that suggest area
    # (note: Overpass may require the "name" tag as well)
    return any(
        (
            v in _AREA_TAG_VALUES_ONE_OF.get(k, ())
            or v not in _AREA_TAG_VALUES_NONE_OF.get(k, (v,))
            for k, v in tags.items()
        )
    )


_AREA_TAG_NAMES = {
    "area",
    "area:highway",
    "amenity",
    "boundary",
    "building",
    "building:part",
    "craft",
    "golf",
    "historic",
    "indoor",
    "landuse",
    "leisure",
    "military",
    "office",
    "place",
    "public_transport",
    "ruins",
    "shop",
    "tourism",
    # for relations
    "admin_level",
    "postal_code",
    "addr:postcode",
}

_AREA_TAG_VALUES_ONE_OF = {
    "barrier": {"city_wall", "ditch", "hedge", "retaining_wall", "wall", "spikes"},
    "highway": {"services", "rest_area", "escape", "elevator"},
    "power": {"plant", "substation", "generator", "transformer"},
    "railway": {"station", "turntable", "roundhouse", "platform"},
    "waterway": {"riverbank", "dock", "boatyard", "dam"},
    # for relations
    "type": {"multipolygon"},
}

_AREA_TAG_VALUES_NONE_OF = {
    "aeroway": {"no", "taxiway"},
    "man_made": {"no", "cutline", "embankment", "pipeline"},
    "natural": {"no", "coastline", "cliff", "ridge", "arete", "tree_row"},
}
