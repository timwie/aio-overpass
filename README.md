<h1 align="center">
aio-overpass

[![GitHub Workflow Status](https://img.shields.io/github/actions/workflow/status/timwie/aio-overpass/ci.yml)](https://github.com/timwie/aio-overpass/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/timwie/aio-overpass/branch/main/graph/badge.svg?token=YX1218U740)](https://codecov.io/gh/timwie/aio-overpass)
[![PyPI version](https://badge.fury.io/py/aio_overpass.svg)](https://badge.fury.io/py/aio_overpass)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/aio-overpass)
</h1>

A client for the [Overpass API], a read-only API that serves up custom selected
parts of [OpenStreetMap] data. It is optimized for data consumers that need a few
elements within a glimpse or up to roughly 10 million elements in some minutes,
both selected by search criteria like location, type of objects, tag properties,
proximity, or combinations of them. To make use of it, you should familiarize yourself
with [Overpass QL], the query language used to select the elements that you want.

#### Contents
- [Features](#features)
- [Getting Started](#getting-started)
  - [Choosing Extras](#choosing-extras)
- [Basic Usage](#basic-usage)
  - [Example](#example)
- [Motivation](#motivation)
- [Related Projects](#related-projects)
- [License](#license)

#### See also
- API reference is forthcoming :construction: 
- The version history is available in [CHANGELOG.md](CHANGELOG.md).
- Contributor guide is forthcoming :construction:

<br>

## Features
- Asynchronous requests using [aiohttp]
- Concurrent queries
- Respects rate limits
- Fault tolerance through (customizable) retries
- **Extensions**
  - Typed elements that simplify browsing result sets
  - [Shapely] geometries for manipulation and analysis
  - [GeoJSON] exports
  - Simplified querying and processing of public transportation routes

<br>

## Getting Started
```
pip install aio-overpass
pip install aio-overpass[shapely, networkx, joblib]

poetry add aio-overpass
poetry add aio-overpass[shapely, networkx, joblib]
```

### Choosing Extras
This library can be installed with a number of optional extras.

- Install no extras, if you're fine with `dict` result sets.

- Install the `shapely` extra, if you would like the convenience of typed OSM elements.
  It is also useful if you are interested in elements' geometries,
  and either already use Shapely, or want a simple way to export [GeoJSON] or [WKT].

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

- Install the `joblib` extra to speed up `pt_ordered.collect_ordered_routes`, which can benefit
  greatly from parallelization.

<br>

## Basic Usage
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

### Example
#### Results as Dictionaries
```
from aio_overpass import Client, Query

query = Query("way(24981342); out geom;")

client = Client()

await client.run_query(query)

query.result_set
```

```
{
    ...
    "elements": [
        {
            "type": "way",
            "id": 24981342,
            ...
            "tags": {
                "addr:city": "Hamburg",
                "addr:country": "DE",
                "addr:housename": "Elbphilharmonie",
                ...
            },
        }
    ],
}
```

#### Results as Objects
```
from aio_overpass.element import collect_elements

elems = collect_elements(query)

elems[0].tags
```

```
{
    "addr:city": "Hamburg",
    "addr:country": "DE",
    "addr:housename": "Elbphilharmonie",
    ...
}

```

#### Results as GeoJSON
```
import json

json.dumps(elems[0].geojson, indent=4)
```

```
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
        "bounds": [
            53.540877,
            9.9832434,
            53.5416212,
            9.9849674
        ]
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

## Motivation

### Goals
- A small and stable set of core functionality.
- Good defaults for queries and retrying.
- Room for extensions that simplify querying and/or processing of spatial data
  in specific problem domains.
- Sensible and spec-compliant GeoJSON exports for all objects that represent spatial features.
- Detailed documentation that supplements learning about OSM and the Overpass API.

### Non-Goals
- Any sort of Python interface to replace writing Overpass QL code.
- Integrating other OSM-related services (like the OSM API or Nominatim)
- Command line interface

<br>

## Related Projects
- [Overpass API](https://github.com/drolbr/Overpass-API)
- [Overpass Turbo], the best choice to prototype your queries in a browser
- [Folium], which can be used to visualize GeoJSON on [Leaflet] maps
- [OSMnx], which is specialized on street networks
- [overpass-api-python-wrapper], another Python client for the Overpass API
- [overpy], another Python client for the Overpass API
- [OSMPythonTools], a Python client for OSM-related services 
- [overpassify], a Python to Overpass QL transpiler

<br>

## License
Distributed under the MIT License. See `LICENSE` for more information.


[Overpass API]: https://wiki.openstreetmap.org/wiki/Overpass_API
[Overpass QL]: https://wiki.openstreetmap.org/wiki/Overpass_API/Overpass_QL
[OpenStreetMap]: https://www.openstreetmap.org

[Overpass Turbo]: http://overpass-turbo.eu/
[Folium]: https://python-visualization.github.io/folium/
[Leaflet]: https://leafletjs.com/
[overpass-api-python-wrapper]: https://github.com/mvexel/overpass-api-python-wrapper
[overpy]: https://github.com/DinoTools/python-overpy
[OSMnx]: https://github.com/gboeing/osmnx
[OSMPythonTools]: https://github.com/mocnik-science/osm-python-tools
[overpassify]: https://github.com/gappleto97/overpassify

[aiohttp]: https://docs.aiohttp.org/en/stable/
[Joblib]: https://joblib.readthedocs.io/en/latest/
[NetworkX]: https://networkx.github.io/
[PyGeodesy]: https://mrjean1.github.io/PyGeodesy/
[Shapely]: https://shapely.readthedocs.io/en/latest/manual.html

[GeoJSON]: https://en.wikipedia.org/wiki/GeoJSON
[WKT]: https://en.wikipedia.org/wiki/Well-known_text_representation_of_geometry
