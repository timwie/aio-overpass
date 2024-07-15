import asyncio

from aio_overpass import Client, Query
from aio_overpass.element import collect_elements
from aio_overpass.query import DefaultQueryRunner
from test.integration import get_logger
from test.util import verify_element


def validate_elements_in_result_set(code: str) -> None:
    logger = get_logger("any element integration test")

    query = Query(code, logger=logger)

    client = Client(
        user_agent="aio-overpass automated test query (https://github.com/timwie/aio-overpass)",
        runner=DefaultQueryRunner(cache_ttl_secs=25 * 60),
    )

    loop = asyncio.get_event_loop()

    try:
        loop.run_until_complete(client.run_query(query))
    finally:
        loop.run_until_complete(client.close())

    start = loop.time()
    elements = collect_elements(query)
    end = loop.time()

    logger.info(f"Processed {len(elements)} elements in {end - start:.02f}s")

    start = loop.time()
    for elem in elements:
        verify_element(elem)
    end = loop.time()

    logger.info(f"Validated {len(elements)} elements objects in {end - start:.02f}s")
