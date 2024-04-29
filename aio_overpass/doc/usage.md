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
