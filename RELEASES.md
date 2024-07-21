# Release Notes
All notable changes to this project will be documented in this file.
This project adheres to [Semantic Versioning](http://semver.org/).

## [0.14.0]
### Added
* Add the `Element.base_geometry(_details)` properties to allow properly typed access
  to an element's geometry when the exact type is unknown
* Add the `center` property to `Way` and `Relation`
* Add the `bounds` property to `Way` and `Relation`
* Add the `QueryRejectError.timed_out_after_secs` property
* Add the `QueryRejectError.oom_using_mib` property
* Add the `GiveupCause` class that gives more context to `GiveupErrors`
* Add the `GiveupError.cause` property
* Add the `DefaultQueryRunner.cache_delete()` function, which was internal before

### Changed
* **Breaking**: Move `GeoJsonDict` type from `element` to new `spatial` module
* **Breaking**: Move `SpatialDict` class from `element` to new `spatial` module
* **Breaking**: Move `Spatial` class from `element` to new `spatial` module
* Change `numpy` version requirement for Python `<3.12` to `>=1.23,<3` (from `^1.23`)
* All tag values are strings, but were previously typed as `Any`:
  * Change the type of `Element.tags` to `dict[str, str] | None`, from `dict[str, Any] | None`
  * Change the return type of `Element.tag()` to `str | None`, from `Any`
  * Change the type of `Route.tags` to `dict[str, str]`, from `dict[str, Any]`
  * Change the return type of `Route.tag()` to `str | None`, from `Any`

### Removed
* **Breaking**: Remove export of no longer used `OverpassDict` type alias
* **Breaking**: Remove the `geometry` property from the `Element` base class due to typing violation
* **Breaking**: Remove the `bounds` property from the `Element` base class
* **Breaking**: Remove the `center` property from the `Element` base class

### Fixed
* Fix `Query.reset()` removing the selected logger
* Fix a possible `IndexError` in `OrderedRouteView.paths`
* Fix a bug in `to_ordered_routes()` that would omit the last node of the path between two stops,
  and raise an `AssertionError`

## [0.13.1] – 2024-04-30
### Changed
* Change `numpy` version requirement ahead of new major release to `>=1.26,<3` (from `^1.26`)
* Slight change to string representation of finished queries
* Add sections of the README into the actual documentation

## [0.13.0] – 2024-04-11
### Changed
* **Breaking**: `raise_on_failure` is now a keyword-only argument in `Client.run_query()`
* Relax `aiohttp` version requirement to `^3.9` (from `~3.9`)
* Relax `joblib` version requirement to `^1.3` (from `~1.3`)
* Relax `shapely` version requirement to `^2` (from `~2.0`)
* The string representation of a query without kwargs is now `"query{}"` instead of `"query <no kwargs>"`
* Log a message when a query is done
* Log the error more explicitly when a try fails
* Debug logging when matching Overpass error messages

## [0.12.1] – 2024-01-30
### Fixed
* `Client.run_query()` now makes `POST` requests instead of `GET`
  to prevent `414 URI Too Long` errors for large queries

## [0.12.0] – 2023-12-07
### Added
* Add convenience type guard functions to the `error` module (`is_too_busy()` etc.)
* Add `status_timeout_secs` parameter to `Client`, which limits the duration of
  all status requests
* Add `timeout_secs` parameter to `Client.cancel_queries()`
* Add `ResponseErrorCause` type alias

### Changed
* **Breaking**: Increase `aiohttp` requirement to `~3.9`
* Change `Client.run_query()` to no longer enforce a rate limit before making a request.
  This is because we cannot easily know the total amount of slots at an API server
  that uses load balancing, as the [default server does](https://github.com/timwie/aio-overpass/issues/6).
  Previously this would lead to using a maximum of 6 slots instead of the actual 12 slots.
  The new behavior is to simply adhere to the cooldown duration when the server tells us
  we're making too many requests
* The `[timeout:*]` setting is overwritten if `run_timeout_secs` is set, and the remaining
  time is lower than the current setting. Previously, we would use a query timeout that is
  higher than the request timeout.
* In case that we lower the `[timeout:*]` this way, and previously had a try with equal
  or higher query timeout fail with `EXCEEDED_TIMEOUT`, we give up trying immediately.
* The request in `Client.cancel_queries()` is no longer subject to the concurrency limit
* Shorten `Query.cache_key` to 16 characters instead of 64

### Removed
* **Breaking**: Remove the `Status.concurrency` property, since the reported number of slots
  no longer affects the concurrency
* **Breaking**: Remove the `Query.code` property, which has no real use when there is `Query.input_code`

### Fixed
* Fix `run_timeout_secs` having no effect on query request timeouts

## [0.11.0] – 2023-11-14
### Added
* Add the `should_retry` property to all error classes,
  which is used by the default query runner to decide whether to retry or not
* Add the `ResponseError.is_server_error` property
* Add the `SpatialDict` class, which has the `__geo_interface__` property
  * Compared to the old `Spatial.__geo_interface__`, this property does not
    contain `FeatureCollections`, which is not specified by the protocol
* Add `Spatial.geo_interfaces` to map objects to `SpatialDicts`

### Changed
* **Breaking**: Increased `aiohttp` requirement to `~3.9.0rc0`
* `ResponseError` is reverted to include server-side errors, replacing `ServerError`
* Retry all `ResponseErrors` by default
* In the default runner, only log response bodies of `ResponseErrors` when `is_server_error` is false
* GeoJSON `"bbox"` will use `Element.bounds` if `geometry` is not set
* Add `py.typed` to make the package PEP 561 compatible

### Removed
* **Breaking**: Remove `ServerError`, which reverts the last release's decision
  to split these error cases off `ResponseError`
* **Breaking**: Remove `Spatial.__geo_interface__`

## [0.10.0] – 2023-11-04
### Added
* Add `ServerError`, which is similar to `ResponseError`, but for
  responses with status code >= `500`. The crucial difference is
  that it will be retried by default

### Changed
* **Breaking**: There is now an explicit `numpy` requirement when enabling the `shapely` extra:
  `^1.26` for Python 3.12 and above, and `^1.23` for Python 3.11 and below
* **Breaking**: Change `networkx` requirement from `>=2.7` to `^3`
* **Breaking**: Replaced all fields in `ResponseError`:
  * Remove `request_info`, `history`, `status`, `message`, and `headers`
  * Add `response`, `body`, and `cause`
* **Breaking**: `logger` argument of `Query` can no longer be `None`,
  and defaults to a logger that does nothing
* The default query runner will log `ResponseError.body` if such an error occurs

## [0.9.0] – 2023-10-20
The Python versions supported by this release are 3.10-3.12.

### Added
* Add Python 3.12 support
* Add `__slots__` to a lot of classes
* Add `pt_ordered.to_ordered_routes()` and `to_ordered_route()`
* Add `GeometryDetails`, which provides information on whether an
  element's geometry is "valid"
* Add `Way.geometry_details` and `Relation.geometry_details`
* Add `Status.endpoint`
* Add `Status.nb_running_queries`

### Changed
* **Breaking**: Make `QueryRunner` an abstract class, not a protocol
* **Breaking**: Increased `aiohttp` requirement to `~3.9.0b0`
* Enable `speedups` extra of `aiohttp`
* `Way.geometry` and `Relation.geometry` may now be geometries fixed
  by `shapely` instead of the original geometries by the Overpass API.
  To access the original geometry, use `Way.geometry_details` and
  `Relation.geometry_details`
* `DefaultQueryRunner` no longer blocks the event loop while reading
  from or writing to a cache file
* Add `raise_on_failure` argument to `Client.run_query()`, which can be
  disabled to not raise `Query.error` if a query fails

### Removed
* **Breaking**: Drop Python 3.9 support
* **Breaking**: `collect_elements()` already no longer worked for "area" elements with the previous
  release, but its documentation did not reflect that change

### Fixed
* Fix an error when `RequestTimeout.total_without_query_secs` was set to `None`
* Fix an edge case that would lead to an error if `Query.run_timeout_secs`
  was `None` when a query cooldown occurred
* Fix an edge case where `DefaultQueryRunner` would raise an exception
  if a cache file could not be read
* Fix `collect_ordered_routes()` breaking when a stop position is missing
* Fix `collect_elements()` raising when the result set is empty
* Fix `collect_elements()` breaking when the result set included "area" elements

## [0.8.0] – 2023-10-07
### Added
* Add the `Element.geometry` property

### Changed
* **Breaking**: `Ways` may now also have `Polygon` geometries
* **Breaking**: `Relation` may now have `Polygon` or `MultiPolygon` geometries

### Removed
* **Breaking**: Remove `AreaWay` and `AreaRelation`
  * These subclasses could be confusing since "area" is also specific Overpass terminology
  * There is no good reason to have these subclasses since their only difference
    is easily modelled through the `geometry` property

## [0.7.0] – 2023-10-06
### Added
* Add the `query.RequestTimeout` to configure `aiohttp` request timeouts.
  By default, requests now timeout after `20 + Query.timeout_secs` seconds.
* Add `Query.request_timeout` to get/set a query's `RequestTimeout`
* Add `Query.run_timeout_elapsed`
* Add `CallTimeoutError` that is raised when the `request_timeout` elapses

### Changed
* **Breaking**: Rename `Query.query_duration_secs` to `Query.request_duration_secs`

### Fixed
* Make `maxsize` and `timeout` settings not affect `Query.cache_key`

## [0.6.0] – 2023-09-12
### Changed
* **Breaking**: `Query.maxsize_mib` is now a `float` instead of an `int`

### Fixed
* The default `maxsize` setting was previously 512 B instead of the intended 512 MiB
* Closed ways with `LinearRing` geometries now produce valid GeoJSON `LineString` features.
  Previously the geometry `"type"` used was `"LinearRing"`, which is not a type in GeoJSON
* Fixed the occurrence of `"bbox": (nan, nan, nan, nan)` in GeoJSON exports for features
  with empty geometry
* `Query.nb_tries` is now increased at the very end of a try. Previously, this
  was done at the beginning of a try, and could lead to confusing log messages
  where `nb_tries` was already increased
* The default query runner can now increase the `maxsize` and `timeout` settings
  beyond the defaults. These limits were undocumented before, and are removed now
* The default query runner previously overwrote the cache expiration time
  when the cache was hit. Now cached results truly expire after `cache_ttl_secs`,
  and not later

## [0.5.0] – 2023-09-11
### Added
* Add the `Query.response` property that returns the entire response like the old `Query.result_set`
* Add the `Query.was_cached` property
* Add the `ql` module which was previously private
* Add the `ql.poly_filter()` function
* Add the `ql.one_of_filter()` function
* Add the `element.Element.wikidata_id` property
* Add the `element.Element.wikidata_link` property

### Changed
* **Breaking**: Rename `Query.result_size_mib` to `response_size_mib`
* **Breaking**: `Query.response_size_mib` now returns `None` instead of `0.0` if there is no result set
* **Breaking**: `Query.query_duration_secs` now returns `None` if there is no result set
* **Breaking**: `Query.run_duration_secs` now returns `None` if the query has not been not run yet
* **Breaking**: `Query.timestamp_osm` and `Query.timestamp_areas` now return `datetime` objects instead of `str`
* **Breaking**: `Query.result_set` was confusing, since it returned the entire response, and not only the result
  set. It now returns only the result set, which is at the `"elements"` key in the response
* Changed the way `element.collect_elements()` works: relation members that are not
  themselves in the top-level result set are no longer part of the list of elements
  that is returned. That should make it much more intuitive

### Fixed
* Fix `DefaultQueryRunner` caching: previously results were written to a random subdirectory inside
  the temporary directory, whereas now they are written to files at the top level of the
  temporary directory

## [0.4.0] – 2023-07-28
* **Breaking**: Removed `cache_dir` argument from `DefaultQueryRunner`, which now caches
  in `tempfile.TemporaryDirectory()`
* Added missing docstrings
* Slight updates to existing docstrings
* Added optional `logger` argument to `Query`. All logging output of `aio-overpass`
  is fed into this logger by the `Client` and query runner
* Added and updated log messages in the client and default query runner
* Added optional `cache_ttl_secs` argument to `DefaultQueryRunner`, which limits
  the time a query is cached for

## [0.3.0] – 2023-06-29
* **Breaking**: Drop Python 3.8 support. The Python versions supported by this release are 3.9-3.11.
* **Breaking**: Increased `joblib` dependency to `~1.3`, which makes it ready for Python 3.12 among other things
* **Breaking**: `Query`: `maxsize` properties ending in `_mb` now end in `_mib`
* Relaxed `networkx` dependency to `>=2.7` according to [SPEC 0]
* Fixed doc: `maxsize` is not megabytes, but mebibytes

## [0.2.0] – 2023-06-14
* **Breaking**: `QueryError`: `messages` was renamed to `remarks`
* Add `QueryResponseError`, which is raised for unexpected query responses instead of `QueryError`
* `QueryError` is now similar to `ClientError` in that only objects of its subclasses are raised
* The `repr()` of errors have slightly changed
* Fix incorrect documentation of `collect_routes()`
* Add `concurrency` parameter to `Client`: you can now specify a concurrent
  query limit that caps the server's own, or replaces it if there is none.
* Add `concurrency` field to `Status`

## [0.1.2] – 2023-04-27
* Fix zero timeout which would previously be interpreted as "no timeout"
* Abbreviate `QueryError` messages instead of listing them all:
  ```
  aio_overpass.error.QueryLanguageError: query <no kwargs> failed: 'line 1: parse error: Key expected - '%' found.' (+14 more)
  ```

## [0.1.1] – 2023-04-25
* Fix wrong coordinate order in elements' GeoJSON `bbox`
* Fix wrong repository link in `pyproject.toml`

[0.1.1]: https://github.com/timwie/aio-overpass/releases/tag/v0.1.1
[0.1.2]: https://github.com/timwie/aio-overpass/releases/tag/v0.1.2
[0.1.2.post1]: https://github.com/timwie/aio-overpass/releases/tag/v0.1.2.post1
[0.2.0]: https://github.com/timwie/aio-overpass/releases/tag/v0.2.0
[0.3.0]: https://github.com/timwie/aio-overpass/releases/tag/v0.3.0
[0.4.0]: https://github.com/timwie/aio-overpass/releases/tag/v0.4.0
[0.5.0]: https://github.com/timwie/aio-overpass/releases/tag/v0.5.0
[0.6.0]: https://github.com/timwie/aio-overpass/releases/tag/v0.6.0
[0.7.0]: https://github.com/timwie/aio-overpass/releases/tag/v0.7.0
[0.8.0]: https://github.com/timwie/aio-overpass/releases/tag/v0.8.0
[0.9.0]: https://github.com/timwie/aio-overpass/releases/tag/v0.9.0
[0.10.0]: https://github.com/timwie/aio-overpass/releases/tag/v0.10.0
[0.11.0]: https://github.com/timwie/aio-overpass/releases/tag/v0.11.0
[0.12.0]: https://github.com/timwie/aio-overpass/releases/tag/v0.12.0
[0.12.1]: https://github.com/timwie/aio-overpass/releases/tag/v0.12.1
[0.13.0]: https://github.com/timwie/aio-overpass/releases/tag/v0.13.0
[0.13.1]: https://github.com/timwie/aio-overpass/releases/tag/v0.13.1
[0.14.0]: https://github.com/timwie/aio-overpass/releases/tag/v0.14.0

[SPEC 0]: https://scientific-python.org/specs/spec-0000/
