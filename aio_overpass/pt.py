"""Classes and queries specialized on public transportation routes."""

from collections import Counter
from collections.abc import Generator
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Optional, Union, cast

from aio_overpass._dist import fast_distance
from aio_overpass._ql import one_of_filter, poly_filter
from aio_overpass.element import (
    Bbox,
    GeoJsonDict,
    Node,
    OverpassDict,
    Relation,
    Relationship,
    Spatial,
    Way,
    collect_elements,
)
from aio_overpass.query import Query

import shapely.ops
from shapely.geometry import GeometryCollection, Point, Polygon
from shapely.geometry.base import BaseGeometry


__docformat__ = "google"
__all__ = (
    "Route",
    "Stop",
    "Connection",
    "Vehicle",
    "RouteScheme",
    "RouteQuery",
    "SingleRouteQuery",
    "RoutesWithinQuery",
    "collect_routes",
)


class RouteQuery(Query):
    """
    Base class for queries that produce ``Route`` and ``RouteSegment`` objects.

    Be aware that to build full ``RouteSegment`` objects with tags and geometry, this query loads:
     - every route member
     - every stop area any stop on the route is related to
     - every stop in one of those stop areas

    Args:
        input_code: A query that puts the desired routes into the ``.routes`` set,
                     and optionally, its route masters into the ``.masters`` set
                     (for example by recursing up from ``.routes``).
    """

    def __init__(self, input_code: str, **kwargs) -> None:
        input_code = f"""
            {input_code}
            .routes >> -> .route_members;
            way.route_members -> .route_ways;

            (
                node.route_members[highway=bus_stop];
                node.route_members[public_transport];
                way .route_members[public_transport];
                rel .route_members[public_transport];
            ) -> .route_pt_members;

            .route_pt_members <;
            rel._[public_transport=stop_area]->.stop_areas;
            node(r.stop_areas:"stop")[public_transport=stop_position]->.stop_area_stops;

            .masters out;
            .routes out geom;
            .route_ways out tags;
            .route_pt_members out geom;
            .stop_areas out;
            .stop_area_stops out;
        """

        super().__init__(input_code, **kwargs)


class SingleRouteQuery(RouteQuery):
    """
    A query that produces a single ``Route`` object.

    Args:
        relation_id: the desired route's relation ID
    """

    def __init__(self, relation_id: int, **kwargs) -> None:
        self.relation_id = relation_id

        input_code = f"""
            rel({self.relation_id});
            rel._[type=route]->.routes;
            .routes <<;
            rel._[type=route_master]->.masters;
        """

        super().__init__(input_code, **kwargs)


@dataclass
class RoutesWithinQuery(RouteQuery):
    """
    A query that produces ``Route`` objects for any route within the exterior of a polygon.

    Args:
        polygon: Any route that has at least one member element within this shape
                 will be in the result set of this query. Note that the route members
                 are not limited to this polygon - the majority of a route may in fact
                 be outside of it. This shape should be simplified, since a larger number
                 of coordinates on the exterior will slow down the query.
        vehicles: A list of transportation modes to filter by, or an empty list to include
                  routes of any type. A non-empty list will filter routes by the ``route``
                  key.
    """

    def __init__(
        self, polygon: Polygon, vehicles: Optional[list["Vehicle"]] = None, **kwargs
    ) -> None:
        if not vehicles:
            vehicles = list(Vehicle)

        self.polygon = polygon
        self.vehicles = vehicles

        spatial_filter = poly_filter(self.polygon)
        route_filter = one_of_filter("route", *(v.name.lower() for v in vehicles))
        input_code = f"""
            rel{spatial_filter}{route_filter}[type=route]->.routes;
            rel{spatial_filter}{route_filter}[type=route_master]->.masters;
        """

        super().__init__(input_code, **kwargs)


class _RouteRole(Enum):
    """
    A role in a route relation that is relevant to public transportation.

    References:
        - https://taginfo.openstreetmap.org/relations/route#roles
    """

    STOP = auto()
    PLATFORM = auto()
    NONE = auto()


class Connection(Enum):
    """
    Indicates whether you can enter, exit, or do both at a stop on a route.

    References:
        - https://taginfo.openstreetmap.org/relations/route#roles
    """

    ENTRY_AND_EXIT = auto()
    ENTRY_ONLY = auto()
    EXIT_ONLY = auto()

    @property
    def entry_possible(self) -> bool:
        """``True`` if you can enter at this stop on the route."""
        return self != Connection.EXIT_ONLY

    @property
    def exit_possible(self) -> bool:
        """``True`` if you can exit at this stop on the route."""
        return self != Connection.ENTRY_ONLY

    def __repr__(self) -> str:
        return f"{type(self).__name__}.{self.name}"


@dataclass
class Stop(Spatial):
    """
    A stop on a public transportation route.

    Typically, a stop is modelled as two members in a relation: a stop_position node with the
    'stop' role, and a platform with the 'platform' role. These members may be grouped in
    a common stop_area.

    Attributes:
        idx: stop index on the route
        platform: the platform node, way or relation associated with this stop, if any
        stop_position: the stop position node associated with this stop, if any
        stop_coords: a point that, compared to ``stop_position``, is guaranteed to be on the
                     track of the route whenever it is set. Only set if you are collecting
                     ``RouteSegments``.
    """

    idx: int
    platform: Optional[Relationship]
    stop_position: Optional[Relationship]
    stop_coords: Union[Node, Point, None]

    @property
    def name(self) -> Optional[str]:
        """
        This stop's name.

        If platform and stop position names are the same, that name will be returned.
        Otherwise, the most common name out of platform, stop position, and all related stop areas
        will be returned.
        """
        stop_pos_name = self.stop_position.member.tag("name") if self.stop_position else None
        platform_name = self.platform.member.tag("name") if self.platform else None

        if stop_pos_name == platform_name and stop_pos_name is not None:
            return stop_pos_name

        names = [stop_pos_name, platform_name, *(rel.tag("name") for rel in self.stop_areas)]
        names = [name for name in names if name]

        if not names:
            return None

        counter = Counter(names)
        ((most_common, _),) = counter.most_common(1)
        return most_common

    @property
    def connection(self) -> Connection:
        """Indicates whether you can enter, exit, or do both at this stop."""
        options = [
            _connection(relship) for relship in (self.stop_position, self.platform) if relship
        ]
        return next(
            (opt for opt in options if opt != Connection.ENTRY_AND_EXIT), Connection.ENTRY_AND_EXIT
        )

    @property
    def stop_areas(self) -> set[Relation]:
        """Any stop area related to this stop."""
        return {
            relship_to_stop_area.relation
            for relship_to_route in (self.platform, self.stop_position)
            if relship_to_route
            for relship_to_stop_area in relship_to_route.member.relations
            if relship_to_stop_area.relation.tag("public_transport") == "stop_area"
        }

    @property
    def geojson(self) -> GeoJsonDict:
        """A mapping of this object, using the GeoJSON format."""
        # TODO Stop geojson
        raise NotImplementedError

    @property
    def _stop_point(self) -> Optional[Point]:
        """This is set if we have a point that is on the track of the route."""
        if isinstance(self.stop_coords, Node):
            return self.stop_coords.geometry
        if isinstance(self.stop_coords, Point):
            return self.stop_coords
        return None

    @property
    def _geometry(self) -> GeometryCollection:
        """Collection of ``self.platform``, ``self.stop_position`` and  ``self.stop_coords``."""
        geoms = []

        if self.platform:
            # this can be None if the platform is a relation
            geom: Optional[BaseGeometry] = getattr(self.platform.member, "geometry", None)
            if geom:
                geoms.append(geom)

        if self.stop_position:
            member = cast(Node, self.stop_position.member)
            geoms.append(member.geometry)

        if isinstance(self.stop_coords, Point) and self.stop_coords not in geoms:
            geoms.append(self.stop_coords)

        return GeometryCollection(geoms)

    def __repr__(self) -> str:
        if self.stop_position:
            elem = f"stop_position={self.stop_position.member}"
        elif self.platform:
            elem = f"platform={self.platform.member}"
        else:
            raise AssertionError

        return f"{type(self).__name__}({elem}, name='{self.name}')"


class Vehicle(Enum):
    """
    Most common modes of public transportation.

    References:
        - https://wiki.openstreetmap.org/wiki/Relation:route#Public_transport_routes
    """

    # motor vehicles
    BUS = auto()
    TROLLEYBUS = auto()
    MINIBUS = auto()
    SHARE_TAXI = auto()

    # railway vehicles
    TRAIN = auto()
    LIGHT_RAIL = auto()
    SUBWAY = auto()
    TRAM = auto()

    # boats
    FERRY = auto()

    def __repr__(self) -> str:
        return f"{type(self).__name__}.{self.name}"


class RouteScheme(Enum):
    """
    Tagging schemes for public transportation routes.

    References:
        - https://wiki.openstreetmap.org/wiki/Public_transport#Different_tagging_schemas
        - https://wiki.openstreetmap.org/wiki/Key:public_transport:version
    """

    EXPLICIT_V1 = auto()
    EXPLICIT_V2 = auto()

    ASSUME_V1 = auto()
    ASSUME_V2 = auto()

    OTHER = auto()

    @property
    def version_number(self) -> Optional[int]:
        """Public transport tagging scheme."""
        if self in (RouteScheme.EXPLICIT_V1, RouteScheme.ASSUME_V1):
            return 1
        if self in (RouteScheme.EXPLICIT_V2, RouteScheme.ASSUME_V2):
            return 2
        return None

    def __repr__(self) -> str:
        return f"{type(self).__name__}.{self.name}"


@dataclass
class Route(Spatial):
    """
    A public transportation service route, e.g. a bus line.

    Instances of this class are meant to represent OSM routes using the
    'Public Transport Version 2' (PTv2) scheme. Compared to PTv1, this means f.e. that routes
    with multiple directions (forwards, backwards) are represented by multiple route elements.

    Attributes:
        relation: the underlying relation that describes the path taken by a route,
                  and places where people can embark and disembark from the transit service
        scheme: The tagging scheme that was either assumed, or explicitly set on the route relation.
        stops: a sorted list of stops on this route as they would appear on its timetable,
               which was derived from the ``relation``

    References:
        - https://wiki.openstreetmap.org/wiki/Public_transport
        - https://wiki.openstreetmap.org/wiki/Relation:route#Public_transport_routes
    """

    relation: Relation
    scheme: RouteScheme
    stops: list[Stop]

    @property
    def id(self) -> int:
        """Route relation ID."""
        return self.relation.id

    @property
    def tags(self) -> OverpassDict:
        """
        Tags of the route relation.

        Some tags can be inherited from a route master, if not set already.
        """
        from_relation = self.relation.tags or {}
        from_master = {}

        masters = self.masters
        master = masters[0] if len(masters) == 1 else None

        if master and master.tags is not None:
            from_master = {k: v for k, v in master.tags.items() if k in _TAGS_FROM_ROUTE_MASTER}

        return from_master | from_relation

    def tag(self, key: str, default: Any = None) -> Any:
        """
        Get the tag value for the given key.

        Some tags can be inherited from a route master, if not set already.
        """
        value = self.relation.tag(key, default)
        if value is not default:
            return value

        if key not in _TAGS_FROM_ROUTE_MASTER:
            return default

        masters = self.masters
        master = masters[0] if len(masters) == 1 else None

        if not master:
            return default

        return master.tag(key, default)

    @property
    def ways(self) -> list[Way]:
        """
        The ways making up the path of the route.

        Ways may be ordered, and appear multiple times if a way is travelled on more than once.
        All the ways may be contiguous, but gaps are not uncommon.
        """
        return [
            relship.member
            for relship in self.relation.members
            if isinstance(relship.member, Way) and _role(relship) == _RouteRole.NONE
        ]

    @property
    def masters(self) -> list[Relation]:
        """
        Route master relations this route is a part of.

        By convention, this should be a single relation at most.

        References:
            - https://wiki.openstreetmap.org/wiki/Relation:route_master
        """
        return [
            relship.relation
            for relship in self.relation.relations
            if relship.relation.tag("type") == "route_master"
        ]

    @property
    def name_from(self) -> Optional[str]:
        """
        Name of the start station.

        This is either the value of the relation's ``from`` key, a name derived
        from the route's first stop (see ``Stop.name``), or ``None`` if neither
        is available.
        """
        return self.relation.tag(
            key="from",
            default=self.stops[0].name if self.stops else None,
        )

    @property
    def name_to(self) -> Optional[str]:
        """
        Name of the end station.

        This is either the value of the relation's ``to`` key, a name derived
        from the route's last stop (see ``Stop.name``), or ``None`` if neither
        is available.
        """
        return self.relation.tag(
            key="to",
            default=self.stops[-1].name if len(self.stops) > 1 else None,
        )

    @property
    def name_via(self) -> Optional[str]:
        """
        A name of an important station along the route.

        This is either the value of the relation's ``via`` key, or ``None`` if it is not set.
        """
        return self.relation.tag("via")

    @property
    def name(self) -> Optional[str]:
        """
        The name of the route.

        This is either the value relation's ``name`` key, ``{from_} => {via} => {to}`` if at
        least ``from`` and ``to`` are set, or ``None`` otherwise.
        """
        name_tag = self.tag("name")
        if name_tag:
            return name_tag

        from_ = self.name_from
        via = self.name_via
        to = self.name_to

        if from_ and to and via:
            return f"{from_} => {via} => {to}"

        if from_ and to:
            return f"{from_} => {to}"

        return None

    @property
    def vehicle(self) -> Vehicle:
        """
        The mode of transportation used on this route.

        This value corresponds with the value of the relation's ``route`` key.
        """
        if not self.relation.tags or "route" not in self.relation.tags:
            raise AssertionError
        return Vehicle[self.relation.tags["route"].upper()]

    @property
    def bounds(self) -> Optional[Bbox]:
        """The bounding box around all stops of this route."""
        geom = GeometryCollection([stop._geometry for stop in self.stops if stop._geometry])
        return geom.bounds or None

    @property
    def geojson(self) -> GeoJsonDict:
        """A mapping of this object, using the GeoJSON format."""
        # TODO Route geojson
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"{type(self).__name__}(id={self.relation.id}, name='{self.name}')"


_TAGS_FROM_ROUTE_MASTER = {
    "colour",
    "interval",
    "name",
    "network",
    "opening_hours",
    "operator",
    "ref",
    "school",
    "tourism",
    "wheelchair",
}
"""
Tags that, by convention, can be applied to route masters instead of their routes,
in order to avoid duplication.

References:
    - https://wiki.openstreetmap.org/wiki/Relation:route_master
"""


def collect_routes(query: RouteQuery, perimeter: Optional[Polygon] = None) -> list[Route]:
    # TODO the way 'perimeter' works might be confusing
    """
    Consumes the result set of a query and produces ``Route`` objects.

    The order of elements is *not* retained.

    The result set in the input query will be empty after calling this function.

    Args:
        query: The query that produced a result set of route relations.
        perimeter: If set, ``stops`` at the end will be truncated if they are outside of this
                   polygon. This means stops outside the polygon will still be in the list as
                   long as there is at least one following stop that *is* inside the list.
                   Any relation members in ``members`` will not be filtered.

    Raises:
        ValueError: if the input query has no result set

    Returns:
        all routes in the result set of the input query
    """
    elements = collect_elements(query)
    route_rels = [cast(Relation, elem) for elem in elements if elem.tag("type") == "route"]

    routes = []

    for route_rel in route_rels:
        # Group route relation members per stop:
        # f.e. a platform, and a stop position at the same station.
        stops = list(_stops(route_rel))

        # Filter stops by perimeter: cut off at the last stop that is in the perimeter.
        if perimeter:
            while stops and not perimeter.contains(stops[-1]._stop_point):
                del stops[-1]

        route = Route(
            relation=route_rel,
            scheme=_scheme(route_rel),
            stops=stops,
        )

        routes.append(route)

    return routes


def _scheme(route: Relation) -> RouteScheme:
    """Try to identify a route's tagging scheme."""
    tagged_version = route.tag("public_transport:version")
    if tagged_version == "1":
        return RouteScheme.EXPLICIT_V1
    if tagged_version == "2":
        return RouteScheme.EXPLICIT_V2
    if tagged_version:
        return RouteScheme.OTHER

    # any directed and/or numbered tags like "forward:stop:1" indicate PTv1
    directions = {
        "forward:",
        "forward_",
        "backward:",
        "backward_",
    }
    assume_v1 = any(
        (
            role and (role.startswith(prefix) or role[-1].isnumeric())
            for role, _ in route
            for prefix in directions
        )
    )

    return RouteScheme.ASSUME_V1 if assume_v1 else RouteScheme.ASSUME_V2


def _stops(route_relation: Relation) -> Generator[Stop, None, None]:
    """
    Group route relation members so that each member belongs to the same stop along the route.

    Typically, a stop is represented by a stop position or platform, or both.
    """
    idx = 0

    def to_stop(*selected: Relationship) -> Stop:
        nonlocal idx
        stop_idx = idx
        idx += 1
        return Stop(
            idx=stop_idx,
            platform=next(
                (relship for relship in selected if _role(relship) == _RouteRole.PLATFORM), None
            ),
            stop_position=next(
                (relship for relship in selected if _role(relship) == _RouteRole.STOP), None
            ),
            stop_coords=None,  # set later
        )

    # Consider all route relation members that are tagged or given a role that makes them
    # relevant for public transportation.
    route_members = [
        relship for relship in route_relation.members if _role(relship) is not _RouteRole.NONE
    ]

    # no more than two elements per group (best case: roles "stop" & "platform")
    prev: Optional[Relationship] = None
    for next_ in route_members:
        if not prev:  # case 1: no two members to compare yet
            prev = next_
            continue

        if not _at_same_stop(prev, next_):  # case 2: members are not part of same station
            yield to_stop(prev)
            prev = next_
            continue

        # case 3: members are part of same station
        yield to_stop(prev, next_)
        prev = None

    if prev:
        yield to_stop(prev)


def _connection(relship: Relationship) -> Connection:
    """Returns the connection at the route member, according to its role."""
    if relship.role:
        if relship.role.endswith("_entry_only"):
            return Connection.ENTRY_ONLY

        if relship.role.endswith("_exit_only"):
            return Connection.EXIT_ONLY

    return Connection.ENTRY_AND_EXIT


def _role(relship: Relationship) -> _RouteRole:
    """
    Returns the route member's tagged role, or a fitting fallback.

    If a member is tagged as platform or stop_position, use the role as is.
    Otherwise, assign the roles that fit the member. This means that if there's
    a platform in the route relation, we'll recognize it as such, even if it has
    not been given the platform role (perhaps due to oversight by a contributor).
    """
    if relship.role:
        if relship.role.startswith("platform") or relship.role == "hail_and_ride":
            return _RouteRole.PLATFORM

        if relship.role.startswith("stop"):
            return _RouteRole.STOP

    if (
        relship.member.tag("public_transport") == "platform"
        or relship.member.tag("highway") == "bus_stop"
    ):
        return _RouteRole.PLATFORM

    # The correct tag for this is [public_transport=stop_position], but we'll accept
    # values like [public_transport=station] as well, as long as the member is a node.
    # The assumption is that any node that is not representing a platform is *probably*
    # supposed to represent the stop position.
    if relship.member.type == "node" and relship.member.tag("public_transport"):
        return _RouteRole.STOP

    return _RouteRole.NONE


def _share_stop_area(a: Relationship, b: Relationship) -> bool:
    """``True`` if the given route members share least one common stop area."""
    a_areas = {
        relship.relation.id
        for relship in a.member.relations
        if relship.relation.tag("public_transport") == "stop_area"
    }
    b_areas = {
        relship.relation.id
        for relship in b.member.relations
        if relship.relation.tag("public_transport") == "stop_area"
    }
    return not a_areas.isdisjoint(b_areas)


def _connection_compatible(a: Connection, b: Connection) -> bool:
    """
    Check whether two connections are compatible.

    Returns:
        ``False`` if one of the connections is entry-only, while the other is exit-only,
        ``True`` otherwise.
    """
    if a == Connection.ENTRY_AND_EXIT or b == Connection.ENTRY_AND_EXIT:
        return True

    return a == b


def _at_same_stop(a: Relationship, b: Relationship) -> bool:
    """
    Check if two members of a route belong to the same stop in the timetable.

    Looking at the route on a map makes it trivial to group elements as part of the same station,
    but automating this requires some heuristics: we will look at members' type, role, name, and
    their proximity to each other.

    If members grouped by this function are far apart, they might be mistagged, i.e. there was a
    mix-up with either the stop position, platform or order (f.e. having "forward" & "backward"
    stops listed consecutively in the route, instead of their correct timetable order).
    """
    # require not both exit_only & enter_only at same stop
    if not _connection_compatible(_connection(a), _connection(b)):
        return False

    # require no duplicate role at same stop
    if _role(a) == _role(b) and _role(a) is not _RouteRole.NONE:
        return False

    # same name, assume same stop
    if a.member.tag("name", 0) == b.member.tag("name", 1):
        return True

    # same stop area, assume same stop
    if _share_stop_area(a, b):
        return True

    # assume same stop if close together
    if not a.member._geometry or not b.member._geometry:
        return False

    pt_a, pt_b = shapely.ops.nearest_points(
        a.member._geometry, b.member._geometry
    )  # euclidean nearest
    distance = fast_distance(*pt_a.coords[0], *pt_b.coords[0])
    return distance <= _MAX_DISTANCE_TO_TRACK


_MAX_DISTANCE_TO_TRACK = 30.0  # meters
"""
An expectation of the maximum distance between a stop position and its platform.

The two should typically be pretty close to each other. Effectively, this value
should be lower than any sensible (beeline) distance between two consecutive
stops on the same route. It should not be used as a hard constraint.
"""
