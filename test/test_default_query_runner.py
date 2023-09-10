import json
from pathlib import Path
from test.util import URL_INTERPRETER, VerifyingQueryRunner, mock_response

from aio_overpass import Client, Query
from aio_overpass.query import _EXPIRATION_KEY, __cache_delete, __cache_expire, _fibo_backoff_secs

import pytest


@pytest.mark.asyncio
async def test_caching(mock_response):
    test_dir = Path(__file__).resolve().parent
    data_file = test_dir / "route_data" / "ambiguous_stop_name1.json"
    response_str = data_file.read_text()

    with open(data_file) as file:
        response = json.load(file)

    mock_response.get(
        url=URL_INTERPRETER,
        body=response_str,
        status=200,
    )

    c = Client(runner=VerifyingQueryRunner(cache_ttl_secs=100))

    q1 = Query(input_code="nonsense")
    q2 = Query(input_code="nonsense")
    assert q1.cache_key == q2.cache_key

    __cache_delete(q1)

    await c.run_query(q1)
    del q1.response[_EXPIRATION_KEY]
    assert q1.response == response
    assert not q1.was_cached

    mock_response.get(
        url=URL_INTERPRETER,
        body="{}",
        status=504,
        content_type="application/json",
    )

    await c.run_query(q2)
    del q2.response[_EXPIRATION_KEY]
    assert q2.response == response
    assert q2.was_cached


@pytest.mark.asyncio
async def test_cache_expiration(mock_response):
    test_dir = Path(__file__).resolve().parent
    data_file = test_dir / "route_data" / "ambiguous_stop_name2.json"
    response_str = data_file.read_text()

    with open(data_file) as file:
        response = json.load(file)

    mock_response.get(
        url=URL_INTERPRETER,
        body=response_str,
        status=200,
    )

    c = Client(runner=VerifyingQueryRunner(cache_ttl_secs=100))

    q1 = Query(input_code="nonsense")
    q2 = Query(input_code="nonsense")
    assert q1.cache_key == q2.cache_key

    __cache_delete(q1)

    await c.run_query(q1)
    del q1.response[_EXPIRATION_KEY]
    assert q1.response == response
    assert not q1.was_cached

    __cache_expire(q1)

    mock_response.get(
        url=URL_INTERPRETER,
        body=response_str,
        status=200,
    )

    await c.run_query(q2)
    del q2.response[_EXPIRATION_KEY]
    assert q2.response == response
    assert not q2.was_cached


def test_fibonacci_backoff():
    actual = [_fibo_backoff_secs(nb_tries) for nb_tries in range(12)]
    expected = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144]
    assert actual == expected
