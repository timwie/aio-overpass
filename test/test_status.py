from aio_overpass import Client
from aio_overpass.client import Status

import pytest
from aioresponses import aioresponses


URL_STATUS = "https://overpass-api.de/api/status"


@pytest.mark.asyncio
async def test_idle():
    body = r"""
Connected as: 1807920285
Current time: 2020-07-10T14:56:19Z
Rate limit: 2
2 slots available now.
Currently running queries (pid, space limit, time limit, start time):
    """

    c = Client()

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
        concurrency=2,
    )

    assert actual == expected

    await c.close()


@pytest.mark.asyncio
async def test_idle_with_load_balancing():
    body = r"""
Connected as: 2185740403
Current time: 2023-06-22T21:51:45Z
Announced endpoint: gall.openstreetmap.de/
Rate limit: 6
6 slots available now.
Currently running queries (pid, space limit, time limit, start time):
    """

    c = Client()

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
        concurrency=6,
    )

    assert actual == expected

    await c.close()


@pytest.mark.asyncio
async def test_one_slot_available():
    body = r"""
Connected as: 1807920285
Current time: 2020-11-21T12:45:33Z
Rate limit: 2
Slot available after: 2020-11-21T12:50:26Z, in 293 seconds.
Currently running queries (pid, space limit, time limit, start time):
28314	536870912	60	2020-11-21T12:45:27Z
    """

    c = Client()

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
        concurrency=2,
    )

    assert actual == expected

    await c.close()


@pytest.mark.asyncio
async def test_no_slot_available():
    body = r"""
Connected as: 1807920285
Current time: 2020-11-21T12:45:45Z
Rate limit: 2
Slot available after: 2020-11-21T12:46:05Z, in 20 seconds.
Slot available after: 2020-11-21T12:50:26Z, in 281 seconds.
Currently running queries (pid, space limit, time limit, start time):
    """

    c = Client()

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
        concurrency=2,
    )

    assert actual == expected

    await c.close()
