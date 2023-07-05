<h1 align="center">
aio-overpass

[![GitHub Workflow Status](https://img.shields.io/github/actions/workflow/status/timwie/aio-overpass/test_and_publish.yml)](https://github.com/timwie/aio-overpass/actions/workflows/test_and_publish.yml)
[![codecov](https://codecov.io/gh/timwie/aio-overpass/branch/main/graph/badge.svg?token=YX1218U740)](https://codecov.io/gh/timwie/aio-overpass)
[![PyPI version](https://badge.fury.io/py/aio_overpass.svg)](https://badge.fury.io/py/aio_overpass)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/aio-overpass)
[![API reference](https://img.shields.io/badge/API%20reference-555555)](http://www.timwie.dev/aio-overpass/)
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
- [Coordinates](#coordinates)
- [Motivation](#motivation)
- [Related Projects](#related-projects)
- [License](#license)

#### See also
- An overview of modules, classes and functions can be found in the [API reference](http://www.timwie.dev/aio-overpass/).
- The version history is available in [CHANGELOG.md](https://github.com/timwie/aio-overpass/blob/main/CHANGELOG.md).
- Developers can find some instructions in [CONTRIBUTING.md](https://github.com/timwie/aio-overpass/blob/main/CONTRIBUTING.md).

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
```sh
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
```python
from aio_overpass import Client, Query

query = Query("way(24981342); out geom;")

client = Client()

await client.run_query(query)

query.result_set
```

```python
{
    # ...
    "elements": [
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
    ],
}
```

#### Results as Objects
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

#### Results as GeoJSON
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

## Coordinates
* Geographic point locations are expressed by latitude (`lat`) and longitude (`lon`) coordinates.
  * Latitude is given as an angle that ranges from –90° at the south pole to 90° at the north pole,
    with 0° at the Equator.
  * Longitude is given as an angle ranging from 0° at the Prime Meridian (the line that divides the
    globe into Eastern and Western hemispheres), to +180° eastward and −180° westward.
  * `lat/lon` values are `floats` that are exactly those degrees, just without the ° sign.
* This might help you remember which coordinate is which:
  * If you think of a world map, usually it’s a rectangle.
  * The _long_ side (the largest side) is the longitude.
  * Longitude is the x-axis, and latitude is the y-axis.
* Be wary of coordinate order:
  * The Overpass API explicitly names the coordinates: `{ "lat": 50.2726005, "lon": 10.9521885 }`
  * Shapely geometries returned by this library use `lat/lon` order, which is the order
    stated by [ISO 6709], and seems like the most common order.
  * [GeoJSON], on the other hand, uses `lon/lat` order.
* OpenStreetMap uses the [WGS84] spatial reference system
  used by the Global Positioning System (GPS).
* OpenStreetMap node coordinates have seven decimal places, which gives them centimetric precision.
  However, the position accuracy of GPS data is only [about 10m](https://wiki.openstreetmap.org/wiki/Reliability_of_OSM_coordinates).
  A reasonable display accuracy could be five places, which is precise to
  [1.1 metres](https://wiki.openstreetmap.org/wiki/Precision_of_coordinates)
  at the equator.
* Spatial features that cross the 180th meridian are
  [problematic](https://en.wikipedia.org/wiki/180th_meridian#Software_representation_problems),
  since you go from longitude `180.0` to `-180.0`.
  Such features usually have their geometries split up, like the
  [area of Russia](https://www.openstreetmap.org/relation/60189).

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
- [Overpass API](https://github.com/drolbr/Overpass-API), and the [Overpass API Blog]
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
[Overpass API Blog]: https://dev.overpass-api.de/blog/
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

[WGS84]: https://en.wikipedia.org/wiki/World_Geodetic_System
[ISO 6709]: https://en.wikipedia.org/wiki/ISO_6709
