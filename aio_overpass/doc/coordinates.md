## Coordinates
* Geographic point locations are expressed by latitude (`lat`) and longitude (`lon`) coordinates.
  * Latitude is given as an angle that ranges from –90° at the south pole to 90° at the north pole,
    with 0° at the Equator.
  * Longitude is given as an angle ranging from 0° at the Prime Meridian (the line that divides the
    globe into Eastern and Western hemispheres), to +180° eastward and −180° westward.
  * `lat/lon` values are `floats` that are exactly those degrees, just without the ° sign.
* This might help you remember which coordinate is which:
  * If you think of a world map, usually it’s a rectangle.
  * The *long* side (the largest side) is the longitude.
  * Longitude is the x-axis, and latitude is the y-axis.
* Be wary of coordinate order:
  * The Overpass API explicitly names the coordinates: `{ "lat": 50.2726005, "lon": 10.9521885 }`
  * Shapely geometries returned by this library use `lat/lon` order, which is the order
    stated by [ISO 6709](https://en.wikipedia.org/wiki/ISO_6709), and seems like the most common order.
  * [GeoJSON](https://en.wikipedia.org/wiki/GeoJSON), on the other hand, uses `lon/lat` order.
* OpenStreetMap uses the [WGS84](https://en.wikipedia.org/wiki/World_Geodetic_System) spatial reference system
  used by the Global Positioning System (GPS).
* OpenStreetMap node coordinates have seven decimal places, which gives them centimetric precision.
  However, the position accuracy of GPS data is only
  [about 10m](https://wiki.openstreetmap.org/wiki/Reliability_of_OSM_coordinates).
  A reasonable display accuracy could be five places, which is precise to
  [1.1 metres](https://wiki.openstreetmap.org/wiki/Precision_of_coordinates)
  at the equator.
* Spatial features that cross the 180th meridian are
  [problematic](https://en.wikipedia.org/wiki/180th_meridian#Software_representation_problems),
  since you go from longitude `180.0` to `-180.0`.
  Such features usually have their geometries split up, like the
  [area of Russia](https://www.openstreetmap.org/relation/60189).
