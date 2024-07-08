import gzip
from pathlib import Path

from aio_overpass import Client, Query
from aio_overpass.element import collect_elements
from aio_overpass.pt import RouteQuery, collect_routes
from aio_overpass.pt_ordered import collect_ordered_routes
from test.util import (
    URL_INTERPRETER,
    VerifyingQueryRunner,
    mock_response,
    verify_element,
    verify_route,
)

import pytest


@pytest.mark.asyncio()
async def test_collect_any_element_carabanchel(mock_response):
    test_dir = Path(__file__).resolve().parent
    data_file = test_dir / "large_data" / "any_element_carabanchel.json.gz"

    with gzip.open(data_file, mode="r") as f:
        json_body = f.read().decode("utf-8")

    mock_response.post(
        url=URL_INTERPRETER,
        body=json_body,
        status=200,
    )

    query = Query("mock")

    client = Client(runner=VerifyingQueryRunner())
    await client.run_query(query)
    await client.close()

    elements = collect_elements(query)

    for elem in elements:
        verify_element(elem)


@pytest.mark.asyncio()
async def test_collect_any_route_carabanchel(mock_response):
    test_dir = Path(__file__).resolve().parent
    data_file = test_dir / "large_data" / "any_route_carabanchel.json.gz"

    with gzip.open(data_file, mode="r") as f:
        json_body = f.read().decode("utf-8")

    mock_response.post(
        url=URL_INTERPRETER,
        body=json_body,
        status=200,
    )

    query = RouteQuery("mock")

    client = Client(runner=VerifyingQueryRunner())
    await client.run_query(query)
    await client.close()

    routes = collect_routes(query)

    for route in routes:
        verify_route(route)

    collect_ordered_routes(query, n_jobs=-1)
