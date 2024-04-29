A client for the [Overpass API], a read-only API that serves up custom selected
parts of [OpenStreetMap] data.

The Overpass API is optimized for data consumers that need a few elements within
a glimpse or up to roughly 10 million elements in some minutes, both selected by
search criteria like location, type of objects, tag properties, proximity, or
combinations of them. To make use of it, you should familiarize yourself with
[Overpass QL], the query language used to select the elements that you want.

#### Contents
- [Features](#features)
- [Usage](#usage)
- [Choosing Extras](#choosing-extras)

#### See also
- An overview of modules, classes and functions can be found in the [API reference](http://www.timwie.dev/aio-overpass/)
- The version history is available in [RELEASES.md](https://github.com/timwie/aio-overpass/blob/main/RELEASES.md)
- There are some notebooks to check out in [examples/](https://github.com/timwie/aio-overpass/tree/main/examples)
- Developers can find some instructions in [CONTRIBUTING.md](https://github.com/timwie/aio-overpass/blob/main/CONTRIBUTING.md)
- The Overpass API [repository](https://github.com/drolbr/Overpass-API),
  its [blog](https://dev.overpass-api.de/blog/),
  its [user's manual](https://dev.overpass-api.de/overpass-doc/en/index.html)
  and  its [release notes](https://wiki.openstreetmap.org/wiki/Overpass_API/versions)
- [Overpass Turbo] to prototype your queries in your browser

<br>

## Features
- Asynchronous requests using [aiohttp]
- Parallel queries within rate limits
- Fault tolerance through a (customizable) retry strategy
- **Extras**
  - Typed elements that simplify browsing result sets
  - [Shapely] geometries for manipulation and analysis
  - [GeoJSON] exports
  - Simplified querying and processing of public transportation routes

### Design Goals
- A small and stable set of core functionality.
- Good defaults for queries and retrying.
- Sensible and spec-compliant GeoJSON exports for all objects that represent spatial features.
- Detailed documentation that supplements learning about OSM and the Overpass API.
- Room for extensions that simplify querying and/or processing of spatial data
  in specific problem domains.

<br>

## Usage
There are three basic steps to fetch the spatial data you need:

1. **Formulate a query**
    - Either write your own custom query, f.e. `Query("node(5369192667); out;")`,
    - or use one of the `Query` subclasses, f.e. `SingleRouteQuery(relation_id=1643324)`.

2. **Call the Overpass API**
    - Prepare your client with `client = Client(user_agent=...)`.
    - Use `await client.run_query(query)` to fetch the result set.

3. **Collect results**
    - Either access the raw result dictionaries with `query.result_set`,
    - or use a collector, f.e. `collect_elements(query)` to get a list of typed `Elements`.
    - Collectors are often specific to queries - `collect_routes` requires a `RouteQuery`,
      for instance.

<br>

### Example: looking up a building in Hamburg
#### a) Results as Dictionaries
You may use the `.result_set` property to get a list of all query results
without any extra processing:

```python
from aio_overpass import Client, Query

query = Query('way["addr:housename"=Elbphilharmonie]; out geom;')

client = Client()

await client.run_query(query)

query.result_set
```

```python
[
      {
          "type": "way",
          "id": 24981342,
          # ...
          "tags": {
              "addr:city": "Hamburg",
              "addr:country": "DE",
              "addr:housename": "Elbphilharmonie",
              # ...
          },
      }
]
```

<br>

#### b) Results as Objects
This will give you a user-friendly Python interface
for [nodes](https://www.timwie.dev/aio-overpass/aio_overpass/element.html#Node),
[ways](https://www.timwie.dev/aio-overpass/aio_overpass/element.html#Way),
and [relations](https://www.timwie.dev/aio-overpass/aio_overpass/element.html#Relation).
Here we use the `.tags` property:

```python
from aio_overpass.element import collect_elements

elems = collect_elements(query)

elems[0].tags
```

```python
{
    "addr:city": "Hamburg",
    "addr:country": "DE",
    "addr:housename": "Elbphilharmonie",
    # ...
}

```

<br>

#### c) Results as GeoJSON
The processed elements can also easily be converted to GeoJSON:

```python
import json

json.dumps(elems[0].geojson, indent=4)
```

```json
{
    "type": "Feature",
    "geometry": {
        "type": "Polygon",
        "coordinates": [
            [
                [
                    9.9832434,
                    53.5415472
                ],
                ...
            ]
        ]
    },
    "properties": {
        "id": 24981342,
        "type": "way",
        "tags": {
            "addr:city": "Hamburg",
            "addr:country": "DE",
            "addr:housename": "Elbphilharmonie",
            ...
        },
        ...
    },
    "bbox": [
        9.9832434,
        53.540877,
        9.9849674
        53.5416212,
    ]
}
```

<br>

## Choosing Extras
This library can be installed with a number of optional extras.

- Install no extras, if you're fine with `dict` result sets.

- Install the `shapely` extra, if you would like the convenience of typed OSM elements.
  It is also useful if you are interested in elements' geometries,
  and either already use Shapely, or want a simple way to export [GeoJSON](https://en.wikipedia.org/wiki/GeoJSON).

  - This includes the `pt` module to make it easier to interact with public transportation routes.
    Something seemingly trivial like listing the stops of a route can have unexpected pitfalls,
    since stops can have multiple route members, and may have a range of different tags and roles.
    This submodule will clean up the relation data for you.

- Install the `networkx` extra to enable the `pt_ordered` module, if you want a route's path as a
  simple line from A to B. It is hard to do this consistently, mainly because ways are not always
  ordered, and stop positions might be missing. You can benefit from this submodule if you wish to
  - render a route's path between any two stops
  - measure the route's travelled distance between any two stops
  - validate the order of ways in the relation
  - check if the route relation has gaps

- Install the `joblib` extra to speed up `pt_ordered.collect_ordered_routes()`, which can benefit
  greatly from parallelization.

[aiohttp]: https://docs.aiohttp.org/en/stable/
[GeoJSON]: https://en.wikipedia.org/wiki/GeoJSON
[OpenStreetMap]: https://www.openstreetmap.org
[Overpass API]: https://wiki.openstreetmap.org/wiki/Overpass_API
[Overpass QL]: https://wiki.openstreetmap.org/wiki/Overpass_API/Overpass_QL
[Overpass Turbo]: http://overpass-turbo.eu/
[Shapely]: https://shapely.readthedocs.io/en/latest/manual.html
