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
