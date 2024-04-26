from aio_overpass import Client
from test.util import URL_KILL, VerifyingQueryRunner

import pytest
from aioresponses import aioresponses


@pytest.mark.asyncio
@pytest.mark.xdist_group(name="fast")
async def test_cancel_no_queries():
    body = ""

    c = Client(runner=VerifyingQueryRunner())

    with aioresponses() as m:
        m.get(
            url=URL_KILL,
            body=body,
            status=200,
            content_type="text/plain",
        )

        n_cancelled = await c.cancel_queries()

    assert n_cancelled == 0
    await c.close()


@pytest.mark.asyncio
@pytest.mark.xdist_group(name="fast")
async def test_cancel_one_query():
    body = """
Killing query (pid 7118) from IP 2a02:8108:41c0:2d95:109a:1b1:dacd:c917 ...
Done!
    """

    c = Client(runner=VerifyingQueryRunner())

    with aioresponses() as m:
        m.get(
            url=URL_KILL,
            body=body,
            status=200,
            content_type="text/plain",
        )

        n_cancelled = await c.cancel_queries()

    assert n_cancelled == 1
    await c.close()


@pytest.mark.asyncio
@pytest.mark.xdist_group(name="fast")
async def test_cancel_one_duplicate_query():
    body = """
Killing query (pid 7118) from IP 2a02:8108:41c0:2d95:109a:1b1:dacd:c917 ...
Done!
Killing query (pid 7118) from IP 2a02:8108:41c0:2d95:109a:1b1:dacd:c917 ...
Done!
    """

    c = Client(runner=VerifyingQueryRunner())

    with aioresponses() as m:
        m.get(
            url=URL_KILL,
            body=body,
            status=200,
            content_type="text/plain",
        )

        n_cancelled = await c.cancel_queries()

    assert n_cancelled == 1
    await c.close()


@pytest.mark.asyncio
@pytest.mark.xdist_group(name="fast")
async def test_cancel_two_queries():
    body = """
Killing query (pid 7118) from IP 2a02:8108:41c0:2d95:109a:1b1:dacd:c917 ...
Done!
Killing query (pid 7119) from IP 2a02:8108:41c0:2d95:109a:1b1:dacd:c917 ...
Done!
    """

    c = Client(runner=VerifyingQueryRunner())

    with aioresponses() as m:
        m.get(
            url=URL_KILL,
            body=body,
            status=200,
            content_type="text/plain",
        )

        n_cancelled = await c.cancel_queries()

    assert n_cancelled == 2
    await c.close()
