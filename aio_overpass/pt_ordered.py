"""Collect the routes of a ``RouteQuery`` with optimized geometry."""

import itertools
from collections.abc import Generator
from dataclasses import dataclass, replace
from typing import Any, Callable, Optional, Union, cast

from aio_overpass._dist import fast_distance
from aio_overpass.element import GeoJsonDict, Node, Relation, Relationship, Spatial, Way

import networkx as nx
import shapely.ops
from networkx import MultiDiGraph
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPoint,
    Point,
    Polygon,
)

from .pt import _MAX_DISTANCE_TO_TRACK, Route, RouteQuery, Stop, collect_routes


__docformat__ = "google"
__all__ = (
    "OrderedRouteView",
    "OrderedRouteViewNode",
    "collect_ordered_routes",
)


@dataclass
class OrderedRouteViewNode:
    """
    A node on the path of a route.

    Attributes:
        lon: Node longitude.
        lat: Node latitude.
        way_id: The ID of the way this node is located on.
                ``None`` if this node is a stop position and there was no
                path to this node.
        path_idx: Index in ``OrderedRouteView.paths`` this node is a part of.
        n_seen_stops: The number of visited stops so far.
                      Increases on every stop (``1..=nb_stops``).
        distance: The approximate distance travelled so far, in meters.
    """

    lon: float
    lat: float
    way_id: Optional[int]
    path_idx: int
    n_seen_stops: int
    distance: float


@dataclass
class OrderedRouteView(Spatial):
    """
    A view of a public transportation route with simplified and directed path geometry.

    Views of a route can start at any stop, and end at a later stop.
    They are continouous if between every stop, there is a path of contigious ways.
    This is not the case for route relations that have a gap in their track.

    Attributes:
        route: The viewed route.
        ordering: The visited nodes while trying to walk the shortest paths between pairs of stops,
                  ordered from start to finish. This is an empty list if this is an empty view.
    """

    route: Route
    ordering: list[OrderedRouteViewNode]

    @property
    def is_continuous(self) -> bool:
        """
        True if there's a path between all stops on the route.

        False for empty views.
        """
        if not self.ordering:
            return False

        grouped = itertools.groupby(iterable=self.ordering, key=lambda node: node.path_idx)

        sequence_actual = [n for n, _grp in grouped]
        sequence_continuous = list(range(min(sequence_actual), max(sequence_actual) + 1))

        # True if 'path_idx' never skips any stop when iterating 'ordering'
        return sequence_actual == sequence_continuous

    @property
    def stops(self) -> list[Stop]:
        """All stops of this view where a path either starts or ends."""
        if not self.ordering:
            return []

        has_path_to_idx = {node.n_seen_stops for node in self.ordering}
        has_path_from_idx = {node.n_seen_stops - 1 for node in self.ordering}
        indexes = has_path_to_idx | has_path_from_idx
        indexes.remove(len(self.route.stops))
        return [self.route.stops[i] for i in sorted(indexes)]

    def _split(
        self, predicate: Callable[[OrderedRouteViewNode, OrderedRouteViewNode], bool]
    ) -> Generator["OrderedRouteView", None, None]:
        if len(self.ordering) < 2:
            return

        ordering: list[OrderedRouteViewNode] = []

        for a, b in zip(self.ordering, self.ordering[1:]):
            if predicate(a, b):
                yield replace(self, ordering=ordering)
                ordering = [a]
            else:
                ordering.append(a)

        ordering.append(b)
        yield replace(self, ordering=ordering)

    def _group_by(self, key: Callable[[OrderedRouteViewNode], Any]) -> list["OrderedRouteView"]:
        return list(self._split(predicate=lambda a, b: key(a) != key(b)))

    def gap_split(self) -> list["OrderedRouteView"]:
        """Split this view wherever there's a gap in between stops."""
        return list(self._split(predicate=lambda a, b: b.path_idx > a.path_idx + 1))

    def stop_split(self) -> list["OrderedRouteView"]:
        """Split this view at every stop, returning views between every pair of stops."""
        return self._group_by(key=lambda node: node.path_idx)

    def take(self, first_n: int) -> "OrderedRouteView":
        """Returns the continuous view that connects a maximum number of stops at the beginning."""
        if first_n < 2:
            msg = "cannot take less than two stops"
            raise ValueError(msg)

        pre_gap, *_ = self.gap_split()

        by_stop = itertools.groupby(pre_gap.ordering, key=lambda node: node.path_idx)
        by_stop_truncated = itertools.islice(by_stop, first_n - 1)

        ordering = [node for _, nodes in by_stop_truncated for node in nodes]

        return replace(self, ordering=ordering)

    def trim(self, distance: float) -> "OrderedRouteView":
        """
        Trim this view to some distance in meters.

        Returns:
            the continuous view that is not longer than a given distance,
            starting from the first stop.
        """
        pre_gap, *_ = self.gap_split()

        distance_start = pre_gap.ordering[0].distance

        by_stop = itertools.groupby(pre_gap.ordering, key=lambda node: node.path_idx)

        ordering: list[OrderedRouteViewNode] = []

        for _, nodes_iter in by_stop:
            nodes = list(nodes_iter)
            distance_end = nodes[-1].distance

            if (distance_end - distance_start) > distance:
                break

            ordering.extend(nodes)

        return replace(self, ordering=ordering)

    @property
    def paths(self) -> list[Optional[LineString]]:
        """
        The simple paths between every pair of stops.

        These linestrings are the shortest paths, merged from contiguous ways in the route relation.
        Whenever there is no path between two stops, a `None` element will be inserted into the
        result list.
        """
        max_nb_paths = len(self.stops) - 1

        grouped = itertools.groupby(iterable=self.ordering, key=lambda node: node.path_idx)

        lines: list[Optional[LineString]] = [None for _ in range(max_nb_paths)]

        for n, nodes_iter in grouped:
            nodes = [(node.lat, node.lon) for node in nodes_iter]
            if len(nodes) < 2:
                continue
            line = LineString(nodes)
            lines[n] = line

        return lines

    @property
    def path(self) -> Union[LineString, MultiLineString]:
        """
        The geometry representing the path travelled on this view from the first to last stop.

        This is the result of ordering (a subset of) ways inside a route relation by the order of
        traversal, and concatenating them. The order is found by building shortest paths between
        stops. Whenever stops cannot be reached with the ways that are included in the relation,
        the geometry will be split up. This happens when there are "holes" in the relation.
        """
        paths = self.paths

        if not any(ls for ls in paths):
            return MultiLineString([])

        # group consecutive stretches of lines or None values
        stretches_grouped = itertools.groupby(iterable=paths, key=bool)

        # select all sets of consecutive lines to merge them
        stretches = (line_strings for has_track, line_strings in stretches_grouped if has_track)

        merged_lines = []

        for line_strings in stretches:
            coords: list[list[float]] = []

            for line in line_strings:
                if not coords:
                    coords.extend(line.coords)
                else:
                    coords.extend(
                        line.coords[1:]
                    )  # ignore first coord, it's equal to the previous one

            merged_line = LineString(coords)
            merged_lines.append(merged_line)

        if len(merged_lines) == 1:
            return merged_lines[0]

        return MultiLineString(merged_lines)

    @property
    def geojson(self) -> GeoJsonDict:
        """A mapping of this object, using the GeoJSON format."""
        # TODO OrderedRouteView geojson
        raise NotImplementedError


def collect_ordered_routes(
    query: RouteQuery, perimeter: Optional[Polygon] = None, n_jobs: int = 1
) -> list[OrderedRouteView]:
    """
    Produce ``OrderedRouteViews`` objects from a result set.

    Compare to ``collect_routes()``, this function tries to build the geometry representing the
    path travelled on every route from the first to last stop. If there are no holes in a route's
    relation, this can typically generate a single line string to represent the entire path of
    a route. Note that routes tagged with the PTv1 scheme will be ignored (in an effort to keep
    the implemenation as simple as possible).

    Since we cannot guarantee that relation members are ordered, we have to convert the route into
    a graph, and find the shortest paths between stops. The more complex the graph, and the more
    stops in a relation, the more expensive it is to generate those paths. Parallelizing this is
    highly recommended, even for a small amount of routes (see ``n_jobs``).

    You should use this instead of ``collect_routes()`` if you are particularly interested in a
    route's path. Here are some example use cases:
     - rendering a route's path between any two stops
     - measuring the route's travelled distance between any two stops
     - validating the order of ways in the relation

    Args:
        query: The query that produced a result set of route relations.
        perimeter: If set, ``stops`` and ``paths`` of resulting routes will be limited
                   to the exterior of this polygon. Any relation members in ``members``
                   will not be filtered.
        n_jobs: The number of workers that generate route geometries in parallel.
                Passing ``-1`` will start a worker for each CPU, ``-2`` will start one for
                each CPU but one, and the default ``1`` will not run any parallel workers at all.

    Raises:
        ValueError: if the input query has no result set
        ImportError: if ``n_jobs != 1`` and the ``joblib`` extra is missing

    Returns:
        all routes in the result set of the input query
    """
    if n_jobs != 1:
        import joblib

    routes = collect_routes(query, perimeter)

    if not routes:
        return []

    if len(routes) == 1:
        n_jobs = 1

    views = []
    views_empty = []
    graphs = []

    for route in routes:
        seg = OrderedRouteView(route=route, ordering=[])

        has_geometry = route.scheme.version_number == 2 and len(route.stops) >= 2

        if not has_geometry:
            views_empty.append(seg)
            continue

        # Idea: when converting the route's track to a directed graph with parallel edges
        # and allowing edges to be traversed only once, the linestring we look for is the
        # one that concatenates the shortest paths between every pair of stops.
        track_graph = _route_graph(route.relation)

        # For each stop, try to find a stop position on the route's graph (its track).
        track_nodes = MultiPoint([Point(*node) for node in track_graph.nodes])
        track_ways = MultiLineString([LineString([u, v]) for u, v, _key in track_graph.edges])
        for stop in route.stops:
            stop.stop_coords = _find_stop_coords(stop, track_graph, track_nodes, track_ways)

        views.append(seg)
        graphs.append(track_graph)

    # Try to find linestrings that connect all pairs of stops.
    if n_jobs == 1:
        for seg, route, graph in zip(views, routes, graphs):
            seg.ordering = _paths(graph, targets=[stop._stop_point for stop in route.stops])
    else:
        # Note: keep in mind that these objects have to be serialized to use in a seperate process,
        # which could take a while for large objects.
        parallel_args = [
            (graph, [stop._stop_point for stop in route.stops])
            for route, graph in zip(views, graphs)
        ]

        # TODO think about using joblib.Parallel's "return_as"
        #   => can produce a generator that yields the results as soon as they are available
        with joblib.parallel_backend(backend="loky", n_jobs=n_jobs):
            paths = joblib.Parallel()(joblib.delayed(_paths)(*args) for args in parallel_args)

        for seg, path in zip(views, paths):
            seg.ordering = path

    return [*views, *views_empty]


def _route_graph(rel: Relation) -> MultiDiGraph:
    """
    Build a directed graph of a route's track.

    In this graph…
     - …nodes will be a tuple of lat, lon
     - …nodes are every node of every way (stop positions can lie anywhere on the track)
     - …ways that are listed more than once in the relation have parallel edges
     - …inverse edges are added for each way, unless it is tagged as a oneway
     - …edges remain unweighted for now
    """
    graph = MultiDiGraph()

    track = [relship for relship in rel.members if _is_track(relship)]

    for relship in track:
        way = cast(Way, relship.member)

        data = {_WAY_ID_KEY: way.id}

        if way.tag("oneway") == "no":
            is_oneway = False
        else:
            is_oneway = any((way.tag(k) in v for k, v in _PT_ONEWAY_TAGS.items()))

        if is_oneway:
            add_forward_edges = relship.role != "backward"
            add_backward_edges = not add_forward_edges
        else:
            add_forward_edges = add_backward_edges = True

        if isinstance(way.geometry, Polygon):
            nodes = list(way.geometry.exterior.coords)
        else:
            nodes = list(way.geometry.coords)

        for a, b in zip(nodes, nodes[1:]):
            if add_forward_edges:
                graph.add_edge(a, b, **data)

            if add_backward_edges:
                graph.add_edge(b, a, **data)

    return graph


_PT_ONEWAY_TAGS = {
    "oneway": {"yes"},
    "highway": {"motorway", "motorway_link", "trunk_link", "primary_link"},
    "junction": {"circular", "roundabout"},
}
"""
Tag values that are commonly associated with oneways.

References:
    - https://wiki.openstreetmap.org/wiki/Key:oneway
    - https://github.com/openstreetmap/iD/blob/develop/modules/osm/tags.js#L81
    - https://wiki.openstreetmap.org/wiki/Talk:Key:oneway
"""


def _is_track(relship: Relationship) -> bool:
    return relship.member.type == "way" and (
        not relship.role or not relship.role.startswith("platform")
    )


def _find_stop_coords(
    stop: Stop, track_graph: MultiDiGraph, track_nodes: MultiPoint, track_ways: MultiLineString
) -> Union[Node, Point, None]:
    """
    Find a node on the track that closesly represents the stop position.

    Args:
        stop: the stop to locate on the graph
        track_graph: the graph that represents the route's track
        track_nodes: a point for every node in the graph
        track_ways: a line string for every edge in the graph

    Returns:
     - None if no appropriate node found
     - Some Node if we found a stop position in either relation or a stop relation
     - Some Point if we found a close node on the track, that is *probably* close to the
       actual stop position
    """
    # (a) check if the route relation has a stop_position for this stop
    if stop.stop_position:
        stop_node = cast(Node, stop.stop_position.member)
        if stop_node.geometry.coords[0] in track_graph:
            return stop_node

    # (b) check if a related stop_area has a stop_position for this stop
    station_stop_positions = (
        cast(Node, member)
        for stop_area in stop.stop_areas
        for _, member in stop_area
        if member.tag("public_transport") == "stop_position"
    )

    stop_pos = next(
        (el for el in station_stop_positions if el.geometry.coords[0] in track_graph), None
    )

    if stop_pos:
        return stop_pos

    # (c) use a node on the graph, that is closest to one of the relation members
    station_geom = GeometryCollection(
        [relship.member._geometry for relship in (stop.stop_position, stop.platform) if relship]
    )

    if not track_nodes or not station_geom:
        return None

    # Calculate the distance of the stop geometry to the track geometry.
    a, b = shapely.ops.nearest_points(track_ways, station_geom)  # euclidean nearest

    distance_to_track = fast_distance(*a.coords[0], *b.coords[0])

    # Idea: if the stop is too far away from the track, it cannot be representative.
    if distance_to_track > _MAX_DISTANCE_TO_TRACK:
        return None

    # Find the node in the graph that is closest to the stop.
    a, _ = shapely.ops.nearest_points(track_nodes, station_geom)  # euclidean nearest

    # This node is *probably* representative of the actual stop position for this stop.
    # It is possible though, that the node is actually close to more than one way
    # on the route's track, and that we choose a node that could be far from the
    # actual stop position.
    return a


def _paths(route_graph: MultiDiGraph, targets: list[Optional[Point]]) -> list[OrderedRouteViewNode]:
    """
    Find shortest paths in the directed route graph between every target stop.

    Edge weights are set to the metric distance between two nodes.

    Not every two stops can be connected, f.e. when they have no representative
    position on the route's track, or when that track has gaps.

    Args:
        route_graph: the unweighted, directed graph of the route's track
        targets: the stop positions to connect
    """
    # set edge weights to metric distance
    for u, v in route_graph.edges():
        if _WEIGHT_KEY in route_graph[u][v][0]:
            continue

        distance = fast_distance(*u, *v)  # meters

        for k in route_graph[u][v]:
            route_graph[u][v][k]["weight"] = distance

        if u not in route_graph[v]:  # if no inverse exists
            continue

        for k in route_graph[v][u]:
            route_graph[v][u][k]["weight"] = distance

    traversal = _Traversal(
        targets_left=targets[1:],
        targets_visited=targets[:1],
        ordering=[],
        distance=0.0,
        path_idx=0,
    )

    traversal = _traverse_graph(graph=route_graph, progress=traversal)

    return traversal.ordering


_GraphNode = tuple[float, float]


@dataclass
class _Traversal:
    ordering: list[OrderedRouteViewNode]
    targets_visited: list[Optional[Point]]
    targets_left: list[Optional[Point]]
    distance: float
    path_idx: int


def _traverse_graph(graph: MultiDiGraph, progress: _Traversal) -> _Traversal:
    """Find shortest paths between targets, while discouraging edges to be traversed twice."""
    if len(progress.targets_left) == 0:
        return progress

    a = progress.targets_visited[-1]
    b = progress.targets_left[0]

    u = a.coords[0] if a else None
    v = b.coords[0] if b else None

    if u != v:
        try:
            path_nodes = nx.shortest_path(graph, source=u, target=v, weight=_WEIGHT_KEY)
            next_progress = _traverse_path(graph, progress, path_nodes)
            return _traverse_graph(graph, next_progress)
        except nx.NetworkXNoPath:
            pass

    next_progress = _Traversal(
        ordering=[
            *progress.ordering,
            OrderedRouteViewNode(
                lon=u[1],
                lat=u[0],
                way_id=None,
                path_idx=progress.path_idx,
                n_seen_stops=len(progress.targets_visited),
                distance=progress.distance,
            ),
        ],
        targets_left=progress.targets_left[1:],
        targets_visited=progress.targets_visited + progress.targets_left[:1],
        distance=progress.distance,
        path_idx=progress.path_idx + 1,
    )
    return _traverse_graph(graph, next_progress)


def _traverse_path(
    graph: MultiDiGraph, progress: _Traversal, path_nodes: list[_GraphNode]
) -> _Traversal:
    """
    Walk the path to visit the next stop, and collect path nodes along the way.

    Repeated traversal of the edge (u, v) is discouraged by setting a large, arbitrary weight.
    Implicitly, this discourages repeated traversal of ways in a route relation. Since the path
    members are supposed to be ordered, ways that are repeatedly traversed should appear more than
    once in the relation. But since we cannot guarantee that, flat-out removal of these edges/ways
    would be too drastic.
    """
    if not path_nodes:
        msg = "expected non-empty list of nodes"
        raise ValueError(msg)

    edges = list(zip(path_nodes, path_nodes[1:]))
    n_seen_stops = len(progress.targets_visited)
    new_ordering = []

    for u, v in edges:
        # don't duplicate last visited stop position node
        if (
            progress.ordering
            and progress.ordering[-1].lat == u[0]
            and progress.ordering[-1].lon == u[1]
        ):
            continue

        # The path does not specify exactly which edge was traversed, so we select
        # the parallel edge of (u, v) that has the smallest weight, and increase it.
        u, v, key, _ = min(
            graph.edges([u, v], keys=True, data=True), key=lambda t: t[3][_WEIGHT_KEY]
        )

        graph[u][v][key][_WEIGHT_KEY] += _WEIGHT_MULTIPLIER

        # Also increase weight of the inverse edge
        if graph.has_edge(v, u, key):
            graph[v][u][key][_WEIGHT_KEY] += _WEIGHT_MULTIPLIER

        way_id = graph[u][v][key][_WAY_ID_KEY]

        way_distance = graph[u][v][key][_WEIGHT_KEY] % _WEIGHT_MULTIPLIER

        new_ordering.append(
            OrderedRouteViewNode(
                lon=u[1],
                lat=u[0],
                way_id=way_id,
                path_idx=progress.path_idx,
                n_seen_stops=n_seen_stops,
                distance=progress.distance,
            )
        )

        progress.distance += way_distance

    new_ordering.append(
        OrderedRouteViewNode(
            lon=v[1],
            lat=v[0],
            way_id=way_id,
            path_idx=progress.path_idx,
            n_seen_stops=n_seen_stops + 1,
            distance=progress.distance,
        )
    )

    return _Traversal(
        ordering=progress.ordering + new_ordering,
        targets_left=progress.targets_left[1:],
        targets_visited=progress.targets_visited + progress.targets_left[:1],
        distance=progress.distance,
        path_idx=progress.path_idx + 1,
    )


_WEIGHT_MULTIPLIER: float = 1e10
_WEIGHT_KEY = "weight"
_WAY_ID_KEY = "way"
