import asyncio
import logging
import sys

from aio_overpass import Client, Query
from aio_overpass.element import collect_elements
from aio_overpass.query import DefaultQueryRunner

from ..util import verify_element


assert __name__ == "__main__"

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

code = """
[timeout:60];
area[name="Carabanchel"][boundary=administrative];
nwr(area);
out geom;
"""

query = Query(code)

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

print(f"Processed {len(elements)} elements in {end - start:.02f}s")

start = loop.time()
for elem in elements:
    verify_element(elem)
end = loop.time()

print(f"Validated {len(elements)} elements objects in {end - start:.02f}s")
