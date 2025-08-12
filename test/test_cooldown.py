import logging

from aio_overpass import Client, Query
from aio_overpass.error import GiveupCause, GiveupError
from test.util import URL_INTERPRETER, URL_KILL, URL_STATUS, VerifyingQueryRunner, query_logger

import pytest
from aioresponses import aioresponses


@pytest.mark.asyncio
@pytest.mark.xdist_group(name="fast")
async def test_giveup_by_cooldown(query_logger: logging.Logger):
    status_body_20sec_cooldown = """
Connected as: 1807920285
Current time: 2020-11-21T12:45:45Z
Rate limit: 2
Slot available after: 2020-11-21T12:46:05Z, in 20 seconds.
Slot available after: 2020-11-21T12:50:26Z, in 281 seconds.
Currently running queries (pid, space limit, time limit, start time):
    """

    query_body_too_many_queries = """
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"
    "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
 <html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en">
<head>
  <meta http-equiv="content-type" content="text/html; charset=utf-8" lang="en"/>
  <title>OSM3S Response</title>
 </head>
<body>

<p>The data included in this document is from www.openstreetmap.org. The data is made available under ODbL.</p>
<p><strong style="color:#FF0000">Error</strong>: runtime error: open64: 0 Success /osm3s_v0.7.54_osm_base Dispatcher_Client::request_read_and_idx::rate_limited. Please check /api/status for the quota of your IP address.
 </p>

 </body>
</html>
    """

    c = Client(runner=VerifyingQueryRunner())

    query = Query(input_code="something", logger=query_logger)
    query.run_timeout_secs = 19.0

    with aioresponses() as m:
        m.get(
            url=URL_STATUS,
            body=status_body_20sec_cooldown,
            status=200,
            content_type="text/plain",
        )
        m.post(
            url=URL_INTERPRETER,
            status=429,
            body=query_body_too_many_queries,
            content_type="text/html",
        )

        with pytest.raises(GiveupError) as err:
            await c.run_query(query)

    assert err.value.cause is GiveupCause.RUN_TIMEOUT_BY_COOLDOWN

    with aioresponses() as m:
        m.get(
            url=URL_KILL,
            body="",
            status=200,
            content_type="text/plain",
        )
        await c.close()


@pytest.mark.asyncio
@pytest.mark.xdist_group(name="fast")
async def test_success_after_cooldown(query_logger: logging.Logger):
    status_body_1sec_cooldown = """
Connected as: 1807920285
Current time: 2020-11-21T12:45:45Z
Rate limit: 2
Slot available after: 2020-11-21T12:46:05Z, in 1 seconds.
Slot available after: 2020-11-21T12:50:26Z, in 281 seconds.
Currently running queries (pid, space limit, time limit, start time):
    """

    query_body_too_many_queries = """
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"
    "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
 <html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en">
<head>
  <meta http-equiv="content-type" content="text/html; charset=utf-8" lang="en"/>
  <title>OSM3S Response</title>
 </head>
<body>

<p>The data included in this document is from www.openstreetmap.org. The data is made available under ODbL.</p>
<p><strong style="color:#FF0000">Error</strong>: runtime error: open64: 0 Success /osm3s_v0.7.54_osm_base Dispatcher_Client::request_read_and_idx::rate_limited. Please check /api/status for the quota of your IP address.
 </p>

 </body>
</html>
    """

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

    c = Client(runner=VerifyingQueryRunner())

    query = Query(input_code="something", logger=query_logger)
    query.run_timeout_secs = 19.0

    with aioresponses() as m:
        m.post(
            url=URL_INTERPRETER,
            status=429,
            body=query_body_too_many_queries,
            content_type="text/html",
        )
        m.get(
            url=URL_STATUS,
            body=status_body_1sec_cooldown,
            status=200,
            content_type="text/plain",
        )
        m.post(
            url=URL_INTERPRETER,
            status=200,
            body=query_body_success_empty,
            content_type="application/json",
        )

        await c.run_query(query)

    assert query.done
    assert query.result_set == []

    with aioresponses() as m:
        m.get(
            url=URL_KILL,
            body="",
            status=200,
            content_type="text/plain",
        )
        await c.close()
