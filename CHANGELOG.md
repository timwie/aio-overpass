# Changelog
All notable changes to this project will be documented in this file.
This project adheres to [Semantic Versioning](http://semver.org/).

## [0.1.2] - 2023-04-27
* Fix zero timeout which would previously be interpreted as "no timeout"
* Abbreviate `QueryError` messages instead of listing them all:
  ```
  aio_overpass.error.QueryLanguageError: query <no kwargs> failed: 'line 1: parse error: Key expected - '%' found.' (+14 more)
  ```

## [0.1.1] - 2023-04-25
* Fix wrong coordinate order in elements' GeoJSON `bbox`
* Fix wrong repository link in `pyproject.toml`

[0.1.1]: https://github.com/timwie/aio-overpass/releases/tag/v0.1.1
[0.1.2]: https://github.com/timwie/aio-overpass/releases/tag/v0.1.2
