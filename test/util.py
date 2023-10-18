import json
import re

from shapely import Point

from aio_overpass import Query
from aio_overpass.element import Element, Relationship, Node, Spatial, Bbox
from aio_overpass.pt import Route, RouteScheme, Stop, Connection
from aio_overpass.query import DefaultQueryRunner, QueryRunner

import geojson
import pytest
from aioresponses import aioresponses


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
    assert query.code.count("[timeout:") == 1
    assert query.code.count("[maxsize:") == 1
    assert len(query.cache_key) == 64
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
    if _already_validated(elem):
        return

    assert isinstance(elem, Element)

    assert elem.id >= 0

    for relship in elem.relations:
        assert relship.member is elem
        assert relship in relship.relation.members

    for k, v in (elem.tags or {}).items():
        assert elem.tag(k) == v

    assert elem.type in {"node", "way", "relation"}

    if elem.geometry is not None:
        assert elem.geometry.is_valid

    assert geojson.loads(json.dumps(elem.geojson))  # valid GeoJSON

    assert str(elem)  # just test this doesn't raise
    assert repr(elem)  # just test this doesn't raise

    # elem.tags
    # elem.bounds
    # elem.center
    # elem.meta
    # elem.link
    # elem.wikidata_id
    # elem.wikidata_link


def verify_relationship(relship: Relationship) -> None:
    if _already_validated(relship):
        return

    verify_element(relship.member)
    verify_element(relship.relation)
    if relship.role is not None:
        assert isinstance(relship.role, str) and relship.role


def verify_route(route: Route) -> None:
    if _already_validated(route):
        return

    verify_element(route.relation)

    assert route.scheme in RouteScheme

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

    assert isinstance(route.bounds, tuple)
    assert len(route.bounds) == 4
    assert all(isinstance(c, float) for c in route.bounds)

    # TODO geojson


def verify_stop(stop: Stop) -> None:
    if _already_validated(stop):
        return

    assert stop.idx >= 0

    if stop.platform:
        verify_relationship(stop.platform)

    if stop.stop_position:
        verify_relationship(stop.stop_position)

    if stop.stop_coords is not None:
        if isinstance(stop.stop_coords, Node):
            verify_element(stop.stop_coords)
        else:
            assert isinstance(stop.stop_coords, Point)
            assert stop.stop_coords.is_valid

    if stop.name is not None:
        assert isinstance(stop.name, str) and stop.name

    assert stop.connection in Connection

    for rel in stop.stop_areas:
        verify_element(rel)

    # _stop_point
    # _geometry
    # TODO geojson


# TODO verify OrderedRouteView


def _already_validated(obj: Spatial) -> bool:
    if getattr(obj, "__validated__", False):
        return True
    object.__setattr__(obj, "__validated__", True)
    return False
