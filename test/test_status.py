from aio_overpass import Client
from aio_overpass.client import Status
from aio_overpass.error import ResponseError
from test.util import URL_STATUS, VerifyingQueryRunner

import pytest
from aioresponses import aioresponses


@pytest.mark.asyncio()
@pytest.mark.xdist_group(name="fast")
async def test_idle():
    body = """
Connected as: 1807920285
Current time: 2020-07-10T14:56:19Z
Rate limit: 2
2 slots available now.
Currently running queries (pid, space limit, time limit, start time):
    """

    c = Client(runner=VerifyingQueryRunner())

    with aioresponses() as m:
        m.get(
            url=URL_STATUS,
            body=body,
            status=200,
            content_type="text/plain",
        )

        actual = await c.status()

    expected = Status(
        slots=2,
        free_slots=2,
        cooldown_secs=0,
        endpoint=None,
        nb_running_queries=0,
    )

    assert actual == expected

    await c.close()

    _ = str(actual)
    _ = repr(actual)


@pytest.mark.asyncio()
@pytest.mark.xdist_group(name="fast")
async def test_idle_with_load_balancing():
    body = """
Connected as: 2185740403
Current time: 2023-06-22T21:51:45Z
Announced endpoint: gall.openstreetmap.de/
Rate limit: 6
6 slots available now.
Currently running queries (pid, space limit, time limit, start time):
    """

    c = Client(runner=VerifyingQueryRunner())

    with aioresponses() as m:
        m.get(
            url=URL_STATUS,
            body=body,
            status=200,
            content_type="text/plain",
        )

        actual = await c.status()

    expected = Status(
        slots=6,
        free_slots=6,
        cooldown_secs=0,
        endpoint="gall.openstreetmap.de/",
        nb_running_queries=0,
    )

    assert actual == expected

    await c.close()

    _ = str(actual)
    _ = repr(actual)


@pytest.mark.asyncio()
@pytest.mark.xdist_group(name="fast")
async def test_one_slot_available():
    body = """
Connected as: 1807920285
Current time: 2020-11-21T12:45:33Z
Rate limit: 2
Slot available after: 2020-11-21T12:50:26Z, in 293 seconds.
Currently running queries (pid, space limit, time limit, start time):
28314	536870912	60	2020-11-21T12:45:27Z
    """

    c = Client(runner=VerifyingQueryRunner())

    with aioresponses() as m:
        m.get(
            url=URL_STATUS,
            body=body,
            status=200,
            content_type="text/plain",
        )

        actual = await c.status()

    expected = Status(
        slots=2,
        free_slots=1,
        cooldown_secs=0,
        endpoint=None,
        nb_running_queries=1,
    )

    assert actual == expected

    await c.close()

    _ = str(actual)
    _ = repr(actual)


@pytest.mark.asyncio()
@pytest.mark.xdist_group(name="fast")
async def test_multiple_running_queries():
    body = """
Connected as: 49993325
Current time: 2023-10-19T23:25:17Z
Announced endpoint: none
Rate limit: 0
Currently running queries (pid, space limit, time limit, start time):
2751707	536870912	900	2023-10-19T23:23:40Z
2752374	536870912	180	2023-10-19T23:25:17Z
2752375	536870912	180	2023-10-19T23:25:17Z
    """
    c = Client(runner=VerifyingQueryRunner())

    with aioresponses() as m:
        m.get(
            url=URL_STATUS,
            body=body,
            status=200,
            content_type="text/plain",
        )

        actual = await c.status()

    expected = Status(
        slots=None,
        free_slots=None,
        cooldown_secs=0,
        endpoint=None,
        nb_running_queries=3,
    )

    assert actual == expected

    await c.close()

    _ = str(actual)
    _ = repr(actual)


@pytest.mark.asyncio()
@pytest.mark.xdist_group(name="fast")
async def test_no_slot_available():
    body = """
Connected as: 1807920285
Current time: 2020-11-21T12:45:45Z
Rate limit: 2
Slot available after: 2020-11-21T12:46:05Z, in 20 seconds.
Slot available after: 2020-11-21T12:50:26Z, in 281 seconds.
Currently running queries (pid, space limit, time limit, start time):
    """

    c = Client(runner=VerifyingQueryRunner())

    with aioresponses() as m:
        m.get(
            url=URL_STATUS,
            body=body,
            status=200,
            content_type="text/plain",
        )

        actual = await c.status()

    expected = Status(
        slots=2,
        free_slots=0,
        cooldown_secs=20,
        endpoint=None,
        nb_running_queries=0,
    )

    assert actual == expected

    await c.close()

    _ = str(actual)
    _ = repr(actual)


@pytest.mark.asyncio()
@pytest.mark.xdist_group(name="fast")
async def test_server_error():
    body = """
open64: 2 No such file or directory /osm3s_osm_base Dispatcher_Client::1. Probably the server is down.
    """

    c = Client(runner=VerifyingQueryRunner())

    with aioresponses() as m:
        m.get(
            url=URL_STATUS,
            body=body,
            status=504,
            content_type="text/plain",
        )
        with pytest.raises(ResponseError):
            await c.status()

    await c.close()
