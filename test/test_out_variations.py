from pathlib import Path

from aio_overpass import Client, Query
from aio_overpass.element import Way, collect_elements
from test.util import URL_INTERPRETER, VerifyingQueryRunner, mock_response, verify_element

import pytest


@pytest.mark.asyncio()
@pytest.mark.parametrize(
    "file_name",
    [
        "way_out.json",
        "way_out_bb.json",
        "way_out_body.json",
        "way_out_center.json",
        "way_out_geom.json",
        "way_out_geom_meta.json",
        "way_out_ids.json",
        "way_out_meta.json",
        # "way_out_noids.json",
        "way_out_skel.json",
        "way_out_tags.json",
    ],
)
async def test_way_out_variations(mock_response, file_name: str):
    test_dir = Path(__file__).resolve().parent
    data_file = test_dir / "out_variations" / file_name
    response_str = data_file.read_text()

    mock_response.post(
        url=URL_INTERPRETER,
        body=response_str,
        status=200,
    )

    query = Query("mock")

    client = Client(runner=VerifyingQueryRunner())
    await client.run_query(query)
    await client.close()

    (way,) = collect_elements(query)
    assert isinstance(way, Way)
    verify_element(way)
