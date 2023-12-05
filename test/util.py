import json
import re

from aio_overpass import Query
from aio_overpass.element import Element, Node, Relation, Relationship, Spatial, Way
from aio_overpass.pt import Connection, Route, RouteScheme, Stop
from aio_overpass.query import DefaultQueryRunner, QueryRunner

import geojson
import pytest
import shapely.geometry
from aioresponses import aioresponses
from shapely import Point


URL_INTERPRETER = re.compile(r"^https://overpass-api\.de/api/interpreter\?data=.+$")
URL_STATUS = "https://overpass-api.de/api/status"
URL_KILL = "https://overpass-api.de/api/kill_my_queries"


@pytest.fixture
def mock_response():
    with aioresponses() as m:
        mock_status = """
Connected as: 1807920285
Current time: 2020-11-22T13:32:57Z
Rate limit: 2
2 slots available now.
Currently running queries (pid, space limit, time limit, start time):
        """

        m.get(
            url=URL_STATUS,
            body=mock_status,
            status=200,
        )

        m.get(
            url=URL_KILL,
            body="",
            status=200,
        )

        yield m


# TODO must support concurrent queries
# TODO test that cache_key is stable


class VerifyingQueryRunner(QueryRunner):
    """
    Same as the default runner, but with calls to ``verify_query_state()``
    before and after yielding to it.
    """

    def __init__(self, *args, **kwargs) -> None:
        self._default = DefaultQueryRunner(*args, **kwargs)
        self._prev_nb_tries = None

    async def __call__(self, query: Query) -> None:
        self._verify_nb_tries(query)
        verify_query_state(query)
        await self._default(query)
        verify_query_state(query)

    def _verify_nb_tries(self, query: Query) -> None:
        if self._prev_nb_tries is None:
            msg = "expected zero tries yet"
            assert query.nb_tries == 0, msg
        elif query.nb_tries == 0:
            # was reset
            pass
        else:
            msg = f"expected try #{self._prev_nb_tries + 1} but got {query.nb_tries}"
            assert query.nb_tries == self._prev_nb_tries + 1, msg

        self._prev_nb_tries = query.nb_tries


def verify_query_state(query: Query) -> None:
    """Assert query state consistency."""
    assert query.nb_tries >= 0
    assert query.maxsize_mib >= 0
    assert query.timeout_secs >= 1
    assert query.run_timeout_secs is None or query.run_timeout_secs > 0.0
    # FIXME: assert query._code().count("[timeout:") == 1
    # FIXME: assert query._code().count("[maxsize:") == 1
    assert len(query.cache_key) == 16
    assert query.copyright

    assert str(query)  # just test this doesn't raise
    assert repr(query)  # just test this doesn't raise

    if query.was_cached:
        assert query.nb_tries == 0
        assert query.done
        assert query.error is None
        assert query.response is not None
        assert query.result_set is not None
        assert query.response_size_mib >= 0.0
        assert query.request_duration_secs is None
        assert query.run_duration_secs is None
        assert query.api_version is not None
        assert query.timestamp_osm is not None
        # query.timestamp_areas can be set or not
        return  # don't go into the other blocks

    if query.nb_tries == 0:
        assert not query.done
        assert query.error is None
        assert query.response is None
        assert query.result_set is None
        assert query.response_size_mib is None
        assert query.request_duration_secs is None
        assert query.run_duration_secs is None
        assert query.api_version is None
        assert query.timestamp_osm is None
        assert query.timestamp_areas is None

    if query.error is not None:
        assert not query.done
        assert query.nb_tries > 0
        assert query.response is None
        assert query.result_set is None
        assert query.response_size_mib is None
        assert query.request_duration_secs is None
        assert query.run_duration_secs > 0.0
        assert query.api_version is None
        assert query.timestamp_osm is None
        assert query.timestamp_areas is None

    if query.done:
        assert query.nb_tries > 0
        assert query.error is None
        assert query.response is not None
        assert query.result_set is not None
        assert query.response_size_mib >= 0.0
        assert query.request_duration_secs > 0.0
        assert query.run_duration_secs > 0.0
        assert query.api_version is not None
        assert query.timestamp_osm is not None
        # query.timestamp_areas can be set or not


def verify_element(elem: Element) -> None:
    msg = repr(elem)

    if _already_validated(elem):
        return

    assert isinstance(elem, Element), msg

    assert elem.id >= 0, msg

    for relship in elem.relations:
        assert relship.member is elem, msg
        assert relship in relship.relation.members, msg

    for k, v in (elem.tags or {}).items():
        assert elem.tag(k) == v, msg

    assert elem.type in {"node", "way", "relation"}

    if isinstance(elem, Way | Relation) and elem.geometry:
        assert not elem.geometry_details.valid or elem.geometry_details.valid.is_valid
        assert not elem.geometry_details.accepted or not elem.geometry_details.accepted.is_valid
        assert not elem.geometry_details.invalid or not elem.geometry_details.invalid.is_valid
        assert not elem.geometry_details.invalid or elem.geometry_details.invalid_reason
        assert elem.geometry is elem.geometry_details.best

    assert geojson.loads(json.dumps(elem.geojson)), msg  # valid GeoJSON

    try:
        for spatial_dict in elem.geo_interfaces:
            # TODO "Feature" is unsupported by shapely until shapely 2.1.0 releases
            if spatial_dict.__geo_interface__["type"] != "Feature":
                _ = shapely.geometry.shape(spatial_dict)
    except BaseException as err:
        raise AssertionError(f"{msg}: bad __geo_interface__: {err}")

    assert str(elem), msg  # just test this doesn't raise
    assert repr(elem), msg  # just test this doesn't raise

    # elem.tags
    # elem.bounds
    # elem.center
    # elem.meta
    # elem.link
    # elem.wikidata_id
    # elem.wikidata_link


def verify_relationship(relship: Relationship) -> None:
    msg = repr(relship)

    if _already_validated(relship):
        return

    verify_element(relship.member)
    verify_element(relship.relation)
    if relship.role is not None:
        assert isinstance(relship.role, str) and relship.role, msg

    assert str(relship), msg  # just test this doesn't raise
    assert repr(relship), msg  # just test this doesn't raise


def verify_route(route: Route) -> None:
    msg = repr(route)

    if _already_validated(route):
        return

    verify_element(route.relation)

    assert route.scheme in RouteScheme, msg

    for stop in route.stops:
        verify_stop(stop)

    # id
    # tags
    # tag
    # ways
    # masters
    # name_from
    # name_to
    # name_via
    # name
    # vehicle
    # bounds

    assert isinstance(route.bounds, tuple), msg
    assert len(route.bounds) == 4, msg
    assert all(isinstance(c, float) for c in route.bounds), msg

    assert str(route), msg  # just test this doesn't raise
    assert repr(route), msg  # just test this doesn't raise

    # TODO geojson


def verify_stop(stop: Stop) -> None:
    msg = repr(stop)

    if _already_validated(stop):
        return

    assert stop.idx >= 0, msg

    if stop.platform:
        verify_relationship(stop.platform)

    if stop.stop_position:
        verify_relationship(stop.stop_position)

    if stop.stop_coords is not None:
        if isinstance(stop.stop_coords, Node):
            verify_element(stop.stop_coords)
        else:
            assert isinstance(stop.stop_coords, Point), msg
            assert stop.stop_coords.is_valid, msg

    if stop.name is not None:
        assert isinstance(stop.name, str) and stop.name, msg

    assert stop.connection in Connection, msg

    for rel in stop.stop_areas:
        verify_element(rel)

    assert str(stop), msg  # just test this doesn't raise
    assert repr(stop), msg  # just test this doesn't raise

    # _stop_point
    # _geometry
    # TODO geojson


# TODO verify OrderedRouteView


def _already_validated(obj: Spatial) -> bool:
    if getattr(obj, "__validated__", False):
        return True
    object.__setattr__(obj, "__validated__", True)
    return False
