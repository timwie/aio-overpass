import asyncio

from aio_overpass import Client, Query
from aio_overpass.error import AlreadyRunningError
from aio_overpass.query import DefaultQueryRunner
from test.util import URL_INTERPRETER

import pytest
from aioresponses import aioresponses


@pytest.mark.asyncio
@pytest.mark.xdist_group(name="fast")
async def test_already_running_error_when_lock_acquired():
    query = Query("some code", my_id=0)

    query._run_lock.acquire()

    with pytest.raises(AlreadyRunningError) as err:
        await Client().run_query(query)

    assert err.value.kwargs == {"my_id": 0}


class _BlockingQueryRunner(DefaultQueryRunner):
    def __init__(self, pre_ev: asyncio.Event, post_ev: asyncio.Event) -> None:
        super().__init__(max_tries=1)
        self._pre_ev = pre_ev
        self._post_ev = post_ev

    async def __call__(self, query: Query) -> None:
        self._pre_ev.set()
        await self._post_ev.wait()
        await super().__call__(query)


@pytest.mark.asyncio
@pytest.mark.xdist_group(name="fast")
async def test_already_running_error_when_runner_busy():
    query_body_success_empty = """
    {
      "version": 0.6,
      "generator": "Overpass API 0.7.62.1 084b4234",
      "osm3s": {
        "timestamp_osm_base": "2024-07-21T21:09:02Z",
        "copyright": "The data included in this document is from www.openstreetmap.org. The data is made available under ODbL."
      },
      "elements": [



      ]
    }
        """

    query = Query("some code", my_id=0)

    pre_ev = asyncio.Event()
    post_ev = asyncio.Event()

    regular_client = Client()
    blocking_client = Client(runner=_BlockingQueryRunner(pre_ev, post_ev))

    async def run_with_blocking_client() -> None:
        with aioresponses() as m:
            m.post(
                url=URL_INTERPRETER,
                status=200,
                body=query_body_success_empty,
                content_type="application/json",
            )
            await blocking_client.run_query(query)

    blocking_task = asyncio.create_task(run_with_blocking_client())
    await pre_ev.wait()

    with pytest.raises(AlreadyRunningError) as err:
        await regular_client.run_query(query)

    assert err.value.kwargs == {"my_id": 0}

    # finish running the query
    post_ev.set()
    await blocking_task

    # no longer locked; no error raised
    with aioresponses() as m:
        m.post(
            url=URL_INTERPRETER,
            status=200,
            body=query_body_success_empty,
            content_type="application/json",
        )
        await regular_client.run_query(query)
