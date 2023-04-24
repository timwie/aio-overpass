"""
TODO doc

Adding new route test data:

Enter the following query with your id and date of choice into
[overpass-turbo] and paste the returned data into a json file.

Note: any change made in the production query needs to be reflected here.

```
[out:json][date:"2019-08-26T00:00:00Z"][timeout:60];
rel(1540437)->.routes;
way(r.routes)[oneway=yes]["oneway:bus"!="no"]->.oneways;
.routes >> -> .route_members;
(
    node.route_members[highway=bus_stop];
    node.route_members[public_transport];
    way .route_members[public_transport];
    rel .route_members[public_transport];
) -> .route_station_members;
.route_members <;
rel._[public_transport=stop_area]->.stop_areas;
node(r.stop_areas:"stop")[public_transport=stop_position]->.stop_area_members;
.oneways out tags;
.route_station_members out geom;
.stop_areas out;
.stop_area_members out;
.routes out geom;
// .masters out;
```

[overpass-turbo]: http://overpass-turbo.eu/
"""

import re
from pathlib import Path

from aio_overpass.client import Client
from aio_overpass.pt import RouteQuery, SingleRouteQuery
from aio_overpass.pt_ordered import OrderedRouteView, collect_ordered_routes

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


def mock_result_set(mock_response, file_name):
    test_dir = Path(__file__).resolve().parent
    data_file = test_dir / "route_data" / file_name
    result_set = data_file.read_text()

    mock_response.get(
        url=URL_INTERPRETER,
        body=result_set,
        status=200,
    )


async def run_single_route_query() -> OrderedRouteView:
    query = SingleRouteQuery(relation_id=0)

    client = Client()
    await client.run_query(query)
    await client.close()

    (view,) = collect_ordered_routes(
        query=query,
        perimeter=None,
        n_jobs=1,
    )

    return view


def assert_simple_path(route):
    assert route.ordering, "route has no track geometry"
    assert route.is_continuous, "route has holes in track"

    # assert len(route.paths) == len(route.stops) - 1
    # assert all((path is not None for path in route.paths)), "route has holes in track"
    # assert isinstance(route.path, LineString), "route line string was not merged correctly"


@pytest.mark.asyncio
async def test_simple_linestring(mock_response):
    """
    Subway line with a straightforward track.

    id: 1687358
    timestamp: 2019-08-26
    """
    mock_result_set(mock_response, "simple_linestring.json")
    view = await run_single_route_query()

    assert view.route.id == 1687358
    assert view.route.scheme.version_number == 2
    assert_simple_path(view)
    # TODO simple_linestring


@pytest.mark.asyncio
async def test_ambiguous_stop_name1(mock_response):
    """
    `stop` "Neumühler" vs `platform` Neumühler Kirchenweg";
    but both part of `stop_area` "Neumühler Kirchenweg".

    id: 8543211
    timestamp: 2019-10-04
    """
    mock_result_set(mock_response, "ambiguous_stop_name1.json")
    view = await run_single_route_query()

    assert view.route.scheme.version_number == 2
    assert_simple_path(view)
    # TODO ambiguous_stop_name1


@pytest.mark.asyncio
async def test_ambiguous_stop_name2(mock_response):
    """
    `stop` "Sachsenwaldau" vs `platform` "Ohe, Sachsenwaldau";
    no `stop_area` to resolve conflict.

    id: 1175603
    timestamp: 2019-08-26
    """
    mock_result_set(mock_response, "ambiguous_stop_name2.json")
    view = await run_single_route_query()

    assert view.route.scheme.version_number == 2
    assert_simple_path(view)
    # TODO ambiguous_stop_name2


@pytest.mark.asyncio
async def test_bus_mapping1(mock_response):
    """
    Consistent use of `public_transport=stop_position` and `role=stop`.

    id: 36912
    timestamp: 2019-08-26
    """
    mock_result_set(mock_response, "bus_mapping1.json")
    view = await run_single_route_query()

    assert view.route.scheme.version_number == 2
    assert_simple_path(view)
    # TODO bus_mapping1


@pytest.mark.asyncio
async def test_bus_mapping2(mock_response):
    """
    Consistent use of highway=bus_stop and `role=platform`.

    id: 9361043
    timestamp: 2019-08-26
    """
    mock_result_set(mock_response, "bus_mapping2.json")
    view = await run_single_route_query()

    assert view.route.scheme.version_number == 2
    assert_simple_path(view)
    # TODO bus_mapping2


@pytest.mark.asyncio
async def test_bus_mapping_mixed(mock_response):
    """
    Mixing up `roles`, mixing up `public_transport=stop_position` & `highway=bus_stop`.

    id: 302230
    timestamp: 2019-08-26
    """
    mock_result_set(mock_response, "bus_mapping_mixed.json")
    view = await run_single_route_query()

    assert view.route.scheme.version_number == 2
    assert_simple_path(view)
    # TODO bus_mapping_mixed


@pytest.mark.asyncio
async def test_gap(mock_response):
    """
    Route is disconnected, missing a chunk of street.                                                |

    id: 2635636
    timestamp: 2019-08-26
    """
    mock_result_set(mock_response, "gap.json")
    view = await run_single_route_query()

    assert view.route.scheme.version_number == 2
    assert len(view.path.geoms) == 2
    # TODO gap


@pytest.mark.asyncio
async def test_highway_bus_stop_position(mock_response):
    """
    Stops are tagged with both `highway=bus_stop` & `public_transport=stop_position`,
    which is contradictory.

    id: 8382605
    timestamp: 2019-10-04
    """
    mock_result_set(mock_response, "highway_bus_stop_position.json")
    view = await run_single_route_query()

    assert view.route.scheme.version_number == 2
    assert_simple_path(view)
    # TODO highway_bus_stop_position


@pytest.mark.asyncio
async def test_no_roles(mock_response):
    """
    Only few stops have `role=stop`.

    id: 7924525
    timestamp: 2019-08-26
    """
    mock_result_set(mock_response, "no_roles.json")
    view = await run_single_route_query()

    assert view.route.scheme.version_number == 2
    assert_simple_path(view)
    # TODO no_roles


@pytest.mark.asyncio
async def test_no_stops(mock_response):
    """
    Contains no stops, only ways.

    id: 1185723
    timestamp: 2019-08-26
    """
    mock_result_set(mock_response, "no_stops.json")
    view = await run_single_route_query()

    assert view.route.scheme.version_number == 2
    assert len(view.stops) == 0
    assert len(view.path.geoms) == 0

    assert not view.paths
    assert not view.is_continuous
    assert not view.gap_split()
    assert not view.stop_split()

    with pytest.raises(ValueError):
        view.take(2)

    with pytest.raises(ValueError):
        view.trim(100.0)


@pytest.mark.asyncio
async def test_platform_mismatch(mock_response):
    """
    `platform 335366924` is not the correct one for `stop 706249125`; is unusually far away.

    id: 69555
    timestamp: 2019-08-26
    """
    mock_result_set(mock_response, "platform_mismatch.json")
    view = await run_single_route_query()

    assert view.route.scheme.version_number == 2
    assert_simple_path(view)
    # TODO platform_mismatch


@pytest.mark.asyncio
async def test_platform_relations(mock_response):
    """
    Multiple `platforms` that are of type "relation".

    id: 1540437
    timestamp: 2019-08-26
    """
    mock_result_set(mock_response, "platform_relations.json")
    view = await run_single_route_query()

    assert view.route.scheme.version_number == 2
    assert_simple_path(view)
    # TODO platform_relations


@pytest.mark.asyncio
async def test_recycling_bad(mock_response):
    """
    Bad "recycling" of ways, f.e. stopping twice at `5751451618` would require traversing
    way `610010497` 4 times, only 2 times in relation.

    id: 76833
    timestamp: 2019-08-26
    """
    mock_result_set(mock_response, "recycling_bad.json")
    view = await run_single_route_query()

    assert view.route.scheme.version_number == 2
    assert_simple_path(view)
    # TODO recycling_bad


@pytest.mark.asyncio
async def test_recycling_good(mock_response):
    """
    Good "recycling" of ways, twice-traversed ways are correctly included twice, f.e. `way 8435218`.

    id: 78642
    timestamp: 2019-08-26
    """
    mock_result_set(mock_response, "recycling_good.json")
    view = await run_single_route_query()

    assert view.route.scheme.version_number == 2
    assert_simple_path(view)
    # TODO recycling_good


@pytest.mark.asyncio
async def test_role_mismatch(mock_response):
    """
    `stop 345549806` is `exit_only`, its `platform 1453058506` is not.

    id: 1835068
    timestamp: 2019-08-26
    """
    mock_result_set(mock_response, "role_mismatch.json")
    view = await run_single_route_query()

    assert view.route.scheme.version_number == 2
    assert_simple_path(view)
    # TODO role_mismatch


@pytest.mark.asyncio
async def test_same_stop_no_roles(mock_response):
    """
    Has stops with `stop_position` and platform, but neither have a `role`,
    f.e. nodes 810356724 & 3627059031).

    id: 7893174
    timestamp: 2019-08-26
    """
    mock_result_set(mock_response, "same_stop_no_roles.json")
    view = await run_single_route_query()

    assert view.route.scheme.version_number == 2
    assert_simple_path(view)
    # TODO same_stop_no_roles


@pytest.mark.asyncio
async def test_segmented(mock_response):
    """
    `exit_only (2758626485)` & consecutive `entry_only (2758626488)` at same `stop_area`.                           |

    id: 2635640
    timestamp: 2019-08-26
    """
    mock_result_set(mock_response, "segmented.json")
    view = await run_single_route_query()

    assert view.route.scheme.version_number == 2
    assert_simple_path(view)
    # TODO segmented


@pytest.mark.asyncio
async def test_stop_on_roundabout(mock_response):
    """
    First stop `2130519348` is located on a roundabout.

    id: 2123878
    timestamp: 2019-08-26
    """
    mock_result_set(mock_response, "stop_on_roundabout.json")
    view = await run_single_route_query()

    assert view.route.scheme.version_number == 2
    assert_simple_path(view)
    # TODO stop_on_roundabout


@pytest.mark.asyncio
async def test_stops_in_same_stop_area(mock_response):
    """
    Bus stops on each side of a station (`5944915698` & `5944915696`);
    both part of same `stop_area`.

    id: 72766
    timestamp: 2019-08-26
    """
    mock_result_set(mock_response, "stops_in_same_stop_area.json")
    view = await run_single_route_query()

    assert view.route.scheme.version_number == 2
    assert_simple_path(view)
    # TODO stops_in_same_stop_area


@pytest.mark.asyncio
async def test_unnamed_platforms(mock_response):
    """
    Multiple `platforms` without names.

    id: 60691
    timestamp: 2019-08-26
    """
    mock_result_set(mock_response, "unnamed_platforms.json")
    view = await run_single_route_query()

    assert view.route.scheme.version_number == 2
    assert_simple_path(view)
    # TODO unnamed_platforms


@pytest.mark.asyncio
async def test_with_master(mock_response):
    """
    `route_master` with routes `2557244` & `2557243` for each direction.

    id: 2557495
    timestamp: 2019-08-26
    """
    mock_result_set(mock_response, "with_master.json")

    query = RouteQuery(input_code="")

    client = Client()
    await client.run_query(query)
    await client.close()

    routes = collect_ordered_routes(
        query=query,
        perimeter=None,
    )

    assert len(routes) == 2
    # TODO with_master
