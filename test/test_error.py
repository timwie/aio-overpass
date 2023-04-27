import asyncio
import re

from aio_overpass import Client, Query
from aio_overpass.error import (
    CallError,
    GiveupError,
    QueryError,
    QueryLanguageError,
    QueryRejectCause,
    QueryRejectError,
    ResponseError,
)
from aio_overpass.query import DefaultQueryRunner

import pytest
from aioresponses import CallbackResult, aioresponses


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

        yield m


@pytest.mark.asyncio
async def mock_run_query(mock_response, body, content_type):
    c = Client(runner=DefaultQueryRunner(max_tries=1))
    q = Query("")

    mock_response.get(
        url=URL_INTERPRETER,
        body=body,
        status=200,
        content_type=content_type,
    )

    await c.run_query(q)
    await c.close()


@pytest.mark.asyncio
async def test_too_many_queries(mock_response):
    body = r"""
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

    with pytest.raises(QueryRejectError) as err:
        await mock_run_query(mock_response, body, content_type="text/html")

    assert err.value.cause == QueryRejectCause.TOO_MANY_QUERIES

    expected = [
        "runtime error: open64: 0 Success /osm3s_v0.7.54_osm_base Dispatcher_Client::request_read_and_idx::rate_limited. Please check /api/status for the quota of your IP address."
    ]
    assert err.value.messages == expected

    _ = str(err)
    _ = repr(err)


@pytest.mark.asyncio
async def test_too_busy(mock_response):
    body = r"""
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"
    "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en">
<head>
  <meta http-equiv="content-type" content="text/html; charset=utf-8" lang="en"/>
  <title>OSM3S Response</title>
</head>
<body>

<p>The data included in this document is from www.openstreetmap.org. The data is made available under ODbL.    </p>
<p><strong style="color:#FF0000">Error</strong>: runtime error: open64: 0 Success /osm3s_v0.7.54_osm_base     Dispatcher_Client::request_read_and_idx::timeout. The server is probably too busy to handle your request.
 </p>

</body>
</html>
    """

    with pytest.raises(QueryRejectError) as err:
        await mock_run_query(mock_response, body, content_type="text/html")

    assert err.value.cause == QueryRejectCause.TOO_BUSY

    expected = [
        "runtime error: open64: 0 Success /osm3s_v0.7.54_osm_base     Dispatcher_Client::request_read_and_idx::timeout. The server is probably too busy to handle your request."
    ]
    assert err.value.messages == expected

    _ = str(err)
    _ = repr(err)


@pytest.mark.asyncio
async def test_other_query_error(mock_response):
    body = r"""
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
<p><strong style="color:#FF0000">Error</strong>: runtime error: open64: 2 No such file or directory /osm3s_v0.7.54_osm_base Dispatcher_Client::1 </p>

</body>
</html>
    """

    with pytest.raises(QueryError) as err:
        await mock_run_query(mock_response, body, content_type="text/html")

    expected = [
        "runtime error: open64: 2 No such file or directory /osm3s_v0.7.54_osm_base Dispatcher_Client::1"
    ]
    assert err.value.messages == expected

    _ = str(err)
    _ = repr(err)


@pytest.mark.asyncio
async def test_syntax_error(mock_response):
    body = r"""
<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"    "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en">
   <head>
      <meta http-equiv="content-type" content="text/html; charset=utf-8" lang="en"/>
      <title>OSM3S Response</title>
   </head>
   <body>
      <p>The data included in this document is from www.openstreetmap.org. The data is made available under ODbL.</p>
      <p><strong style="color:#FF0000">Error</strong>: line 1: parse error: Key expected - '%' found. </p>
      <p><strong style="color:#FF0000">Error</strong>: line 1: parse error: '!', '~', '=', '!=', or ']'  expected - '%' found. </p>
      <p><strong style="color:#FF0000">Error</strong>: line 1: parse error: Value expected - '%' found. </p>
      <p><strong style="color:#FF0000">Error</strong>: line 1: parse error: ',' or ']' expected - '%' found. </p>
      <p><strong style="color:#FF0000">Error</strong>: line 1: parse error: Key expected - '%' found. </p>
      <p><strong style="color:#FF0000">Error</strong>: line 1: parse error: '!', '~', '=', '!=', or ']'  expected - '%' found. </p>
      <p><strong style="color:#FF0000">Error</strong>: line 1: parse error: Value expected - '%' found. </p>
      <p><strong style="color:#FF0000">Error</strong>: line 1: parse error: ',' or ']' expected - '%' found. </p>
      <p><strong style="color:#FF0000">Error</strong>: line 1: static error: For the attribute "k" of the element "has-kv" the only allowed values are non-empty strings. </p>
      <p><strong style="color:#FF0000">Error</strong>: line 1: static error: For the attribute "k" of the element "has-kv" the only allowed values are non-empty strings. </p>
      <p><strong style="color:#FF0000">Error</strong>: line 1: parse error: Key expected - '%' found. </p>
      <p><strong style="color:#FF0000">Error</strong>: line 1: parse error: '!', '~', '=', '!=', or ']'  expected - '%' found. </p>
      <p><strong style="color:#FF0000">Error</strong>: line 1: parse error: Value expected - '%' found. </p>
      <p><strong style="color:#FF0000">Error</strong>: line 1: parse error: ',' or ']' expected - '%' found. </p>
      <p><strong style="color:#FF0000">Error</strong>: line 1: static error: For the attribute "k" of the element "has-kv" the only allowed values are non-empty strings. </p>
   </body>
</html>

    """

    with pytest.raises(QueryLanguageError) as err:
        await mock_run_query(mock_response, body, content_type="text/html")

    expected = [
        r"""line 1: parse error: Key expected - '%' found.""",
        r"""line 1: parse error: '!', '~', '=', '!=', or ']'  expected - '%' found.""",
        r"""line 1: parse error: Value expected - '%' found.""",
        r"""line 1: parse error: ',' or ']' expected - '%' found.""",
        r"""line 1: parse error: Key expected - '%' found.""",
        r"""line 1: parse error: '!', '~', '=', '!=', or ']'  expected - '%' found.""",
        r"""line 1: parse error: Value expected - '%' found.""",
        r"""line 1: parse error: ',' or ']' expected - '%' found.""",
        r"""line 1: static error: For the attribute "k" of the element "has-kv" the only allowed values are non-empty strings.""",
        r"""line 1: static error: For the attribute "k" of the element "has-kv" the only allowed values are non-empty strings.""",
        r"""line 1: parse error: Key expected - '%' found.""",
        r"""line 1: parse error: '!', '~', '=', '!=', or ']'  expected - '%' found.""",
        r"""line 1: parse error: Value expected - '%' found.""",
        r"""line 1: parse error: ',' or ']' expected - '%' found.""",
        r"""line 1: static error: For the attribute "k" of the element "has-kv" the only allowed values are non-empty strings.""",
    ]
    assert err.value.messages == expected

    _ = str(err)
    _ = repr(err)


@pytest.mark.asyncio
async def test_other_query_error_remark(mock_response):
    # https://listes.openstreetmap.fr/wws/arc/overpass/2016-05/msg00002.html
    # https://community.openstreetmap.org/t/altere-karte-als-png/71872/6
    # https://wiki.openstreetmap.org/wiki/Overpass_API/status#Won't_fix_2015-02-05

    body = r"""
{
  "version": 0.6,
  "generator": "Overpass API 0.7.56.3 eb200aeb",
  "osm3s": {
    "timestamp_osm_base": "2020-07-10T02:51:02Z",
    "copyright": "The data included in this document is from www.openstreetmap.org. The data is made available under ODbL."
  },
  "elements": [
  ],
"remark": "runtime error: Way 547230203 cannot be expanded at timestamp 2018-05-08T15:48:01Z."
}
    """

    with pytest.raises(QueryError) as err:
        await mock_run_query(mock_response, body, content_type="application/json")

    expected = [
        "runtime error: Way 547230203 cannot be expanded at timestamp 2018-05-08T15:48:01Z."
    ]
    assert err.value.messages == expected

    _ = str(err)
    _ = repr(err)


@pytest.mark.asyncio
async def test_exceeded_maxsize(mock_response):
    body = r"""
{
  "version": 0.6,
  "generator": "Overpass API 0.7.56.3 eb200aeb",
  "osm3s": {
    "timestamp_osm_base": "2020-07-10T02:51:02Z",
    "copyright": "The data included in this document is from www.openstreetmap.org. The data is made available under ODbL."
  },
  "elements": [
  ],
"remark": "runtime error: Query run out of memory in \"recurse\" at line 1 using about 541 MB of RAM."
}
    """

    with pytest.raises(QueryRejectError) as err:
        await mock_run_query(mock_response, body, content_type="application/json")

    assert err.value.cause == QueryRejectCause.EXCEEDED_MAXSIZE

    expected = [
        r"""runtime error: Query run out of memory in "recurse" at line 1 using about 541 MB of RAM.""",
    ]
    assert err.value.messages == expected

    _ = str(err)
    _ = repr(err)


@pytest.mark.asyncio
async def test_exceeded_timeout(mock_response):
    body = r"""
{
  "version": 0.6,
  "generator": "Overpass API 0.7.56.3 eb200aeb",
  "osm3s": {
    "timestamp_osm_base": "2020-07-10T02:51:02Z",
    "copyright": "The data included in this document is from www.openstreetmap.org. The data is made available under ODbL."
  },
  "elements": [
  ],
"remark": "runtime error: Query timed out in \"query\" at line 3 after 2 seconds."
}
    """

    with pytest.raises(QueryRejectError) as err:
        await mock_run_query(mock_response, body, content_type="application/json")

    assert err.value.cause == QueryRejectCause.EXCEEDED_TIMEOUT

    expected = [
        r"""runtime error: Query timed out in "query" at line 3 after 2 seconds.""",
    ]
    assert err.value.messages == expected

    _ = str(err)
    _ = repr(err)


@pytest.mark.asyncio
async def test_connection_refused():
    c = Client(runner=DefaultQueryRunner(max_tries=1))
    q = Query("")

    with aioresponses(), pytest.raises(CallError) as err:
        await c.run_query(q)

    _ = str(err)
    _ = repr(err)


@pytest.mark.asyncio
async def test_internal_server_error():
    c = Client(runner=DefaultQueryRunner(max_tries=1))
    q = Query("")

    with aioresponses() as m, pytest.raises(ResponseError) as err:
        m.get(URL_STATUS, status=500, repeat=True)
        await c.run_query(q)

    _ = str(err)
    _ = repr(err)


@pytest.mark.asyncio
async def test_timeout_error():
    c = Client(runner=DefaultQueryRunner(max_tries=1))
    q = Query("")

    with aioresponses() as m:
        m.get(URL_STATUS, exception=asyncio.TimeoutError())

        with pytest.raises(GiveupError) as err:
            await c.run_query(q)

    _ = str(err)
    _ = repr(err)
