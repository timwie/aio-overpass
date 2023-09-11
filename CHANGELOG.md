# Changelog
All notable changes to this project will be documented in this file.
This project adheres to [Semantic Versioning](http://semver.org/).

<br>

## [0.6.0] – 2023-09-12
### Changed
* `Query.maxsize_mib` is now a `float` instead of an `int`

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

<br>

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
* Changed the way `element.collect_elements()` works: relation members that are not
  themselves in the top-level result set are no longer part of the list of elements
  that is returned. That should make it much more intuitive
* `Query.result_set` was confusing, since it returned the entire response, and not only the result
  set. It now returns only the result set, which is at the `"elements"` key in the response
* Rename `Query.result_size_mib` to `response_size_mib`
* `Query.response_size_mib` now returns `None` instead of `0.0` if there is no result set
* `Query.query_duration_secs` now returns `None` if there is no result set
* `Query.run_duration_secs` now returns `None` if the query has not been not run yet
* `Query.timestamp_osm` and `Query.timestamp_areas` now return `datetime` objects instead of `str`

### Fixed
* Fix `DefaultQueryRunner` caching: previously results were written to a random subdirectory inside
  the temporary directory, whereas now they are written to files at the top level of the
  temporary directory

<br>

## [0.4.0] – 2023-07-28
* Added missing docstrings
* Slight updates to existing docstrings
* Added optional `logger` argument to `Query`. All logging output of `aio-overpass`
  is fed into this logger by the `Client` and query runner
* Added and updated log messages in the client and default query runner
* Removed `cache_dir` argument from `DefaultQueryRunner`, which now caches
  in `tempfile.TemporaryDirectory()`
* Added optional `cache_ttl_secs` argument to `DefaultQueryRunner`, which limits
  the time a query is cached for

<br>

## [0.3.0] – 2023-06-29
* Drop Python 3.8 support. The Python versions supported by this release are 3.9-3.11.
* Relaxed `networkx` dependency to `>=2.7` according to [SPEC 0]
* Increased `joblib` dependency to `~1.3`, which makes it ready for Python 3.12 among other things
* Fixed doc: `maxsize` is not megabytes, but mebibytes
* `Query`: affected properties ending in `_mb` now end in `_mib`
* Add a section on coordinates to the `README`

<br>

## [0.2.0] – 2023-06-14
* `QueryError`: `messages` was renamed to `remarks`
* Add `QueryResponseError`, which is raised for unexpected query responses
  instead of `QueryError`
* `QueryError` is now similar to `ClientError` in that only objects of
  its subclasses are raised
* The `repr()` of errors have slightly changed
* Fix incorrect documentation of `collect_routes()`
* Add `concurrency` parameter to `Client`: you can now specify a concurrent
  query limit that caps the server's own, or replaces it if there is none.
* Add `concurrency` field to `Status`

<br>

## [0.1.2] – 2023-04-27
* Fix zero timeout which would previously be interpreted as "no timeout"
* Abbreviate `QueryError` messages instead of listing them all:
  ```
  aio_overpass.error.QueryLanguageError: query <no kwargs> failed: 'line 1: parse error: Key expected - '%' found.' (+14 more)
  ```
* [0.1.2.post1]: releases are now automatically published to PyPI when pushing a new tag

<br>

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

[SPEC 0]: https://scientific-python.org/specs/spec-0000/
