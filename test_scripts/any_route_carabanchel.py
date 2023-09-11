import asyncio

from aio_overpass import Client
from aio_overpass.pt import RouteQuery, collect_routes
from aio_overpass.pt_ordered import collect_ordered_routes
from aio_overpass.query import DefaultQueryRunner


assert __name__ == "__main__"

code = """
[timeout:180];
area[name="Carabanchel"][boundary=administrative];
rel(area)[type=route]->.routes;
"""

query = RouteQuery(code)

client = Client(
    user_agent="aio-overpass automated test query (https://github.com/timwie/aio-overpass)",
    runner=DefaultQueryRunner(cache_ttl_secs=5 * 60),
)

loop = asyncio.get_event_loop()

try:
    loop.run_until_complete(client.run_query(query))
finally:
    loop.run_until_complete(client.close())

start = loop.time()
routes = collect_routes(query)
end = loop.time()

print(f"Processed {len(routes)} routes in {end - start:.02f}s")

start = loop.time()
collect_ordered_routes(query, n_jobs=-1)
end = loop.time()

print(f"Processed {len(routes)} ordered routes in {end - start:.02f}s")