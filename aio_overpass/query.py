"""Query state and runner."""

import asyncio
import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Awaitable, Callable, Optional

from aio_overpass.error import (
    ClientError,
    QueryLanguageError,
    QueryRejectCause,
    QueryRejectError,
    ResponseError,
)


__all__ = (
    "Query",
    "QueryRunner",
    "DefaultQueryRunner",
    "DEFAULT_MAXSIZE",
    "DEFAULT_TIMEOUT",
)


DEFAULT_MAXSIZE = 512
"""Default ``maxsize`` setting in megabytes"""

DEFAULT_TIMEOUT = 180
"""Default ``timeout`` setting in seconds"""

_COPYRIGHT = "The data included in this document is from www.openstreetmap.org. The data is made available under ODbL."
"""This is the same copyright notice included in result sets"""

_SETTING_PATTERN = re.compile(r"\[(\w+?):(.+?)]\s*;?")
"""A pattern to match setting declarations (not the entire settings statement)."""


class Query:
    """
    State of a query that is either pending, successful, or failed.

    Args:
        input_code: The input Overpass QL code. Note that some settings might be changed
                    by query runners, notably the 'timeout' and 'maxsize' settings.
        **kwargs: Additional keyword arguments that can be used to identify queries.

    References:
        - https://wiki.openstreetmap.org/wiki/Overpass_API/Overpass_QL
    """

    def __init__(self, input_code: str, **kwargs) -> None:
        self._input_code = input_code
        self._kwargs = kwargs

        self._settings = dict(_SETTING_PATTERN.findall(input_code))

        self._settings["out"] = "json"

        if "maxsize" not in self._settings:
            self._settings["maxsize"] = DEFAULT_MAXSIZE

        if "timeout" not in self._settings:
            self._settings["timeout"] = DEFAULT_TIMEOUT

        self._client_timeout: Optional[float] = None

        # set by the client that executes this query
        self._error: Optional[ClientError] = None
        self._result_set: Optional[dict] = None
        self._result_set_bytes = 0.0
        self._time_end_try = 0.0  # time the most recent try finished
        self._time_start = 0.0  # time prior to executing the first try
        self._time_start_try = 0.0  # time prior to executing the most recent try
        self._nb_tries = 0

    def reset(self) -> None:
        """Reset the query to its initial state, ignoring previous tries."""
        Query.__init__(self, input_code=self._input_code, **self._kwargs)

    @property
    def input_code(self) -> str:
        """The original input Overpass QL source code."""
        return self._input_code

    @property
    def kwargs(self) -> dict:
        """
        Keyword arguments that can be used to identify queries.

        The default query runner will log these values when a query is run.
        """
        return self._kwargs

    @property
    def nb_tries(self) -> int:
        """Current number of tries."""
        return self._nb_tries

    @property
    def error(self) -> Optional[ClientError]:
        """
        Error of the most recent try.

        Returns:
            an error or ``None`` if the query wasn't tried or hasn't failed
        """
        return self._error

    @property
    def result_set(self) -> Optional[dict]:
        """
        The result set of the query.

        This is open data, licensed under the Open Data Commons Open Database License (ODbL).
        You are free to copy, distribute, transmit and adapt this data, as long as you credit
        OpenStreetMap and its contributors. If you alter or build upon this data, you may
        distribute the result only under the same licence.

        References:
            - https://www.openstreetmap.org/copyright
            - https://opendatacommons.org/licenses/odbl/1-0/
        """
        return self._result_set

    @property
    def result_size_mb(self) -> float:
        """The size of the result set in megabytes."""
        return self._result_set_bytes / 1024.0 / 1024.0

    @property
    def maxsize_mb(self) -> int:
        """
        The current value of the [maxsize:*] setting in megabytes.

        This size indicates the maximum allowed memory for the query in bytes RAM on the server,
        as expected by the user. If the query needs more RAM than this value, the server may abort
        the query with a memory exhaustion. The higher this size, the more probably the server
        rejects the query before executing it.
        """
        return int(self._settings["maxsize"]) // 1024 // 1024

    @maxsize_mb.setter
    def maxsize_mb(self, value: int) -> None:
        self._settings["maxsize"] = value * 1024 * 1024

    @property
    def timeout_secs(self) -> int:
        """
        The current value of the [timeout:*] setting in seconds.

        This duration is the maximum allowed runtime for the query in seconds, as expected by the
        user. If the query runs longer than this time, the server may abort the query. The higher
        this duration, the more probably the server rejects the query before executing it.
        """
        return int(self._settings["timeout"])

    @timeout_secs.setter
    def timeout_secs(self, value: int) -> None:
        self._settings["timeout"] = value

    @property
    def run_timeout_secs(self) -> Optional[float]:
        """
        A limit to ``run_duration_secs``, that cancels the query when exceeded.

        Defaults to no timeout.

        The client will raise a ``QueryCancelledError`` if the timeout is reached.

        Not to be confused with ``timeout_secs``, which is a setting for the Overpass API instance,
        that limits the query execution time. Instead, this value can be used to limit the total
        client-side time spent on this query (see ``Client.run_query``).
        """
        return self._client_timeout

    @run_timeout_secs.setter
    def run_timeout_secs(self, value: Optional[float]) -> None:
        self._client_timeout = value

    @property
    def code(self) -> str:
        """
        The Overpass QL source code of this query.

        This is different from ``input_code`` only when it comes to settings.
        """
        settings = "".join((f"[{k}:{v}]" for k, v in self._settings.items())) + ";"

        # Remove the original settings statement
        code = _SETTING_PATTERN.sub("", self._input_code)

        return f"{settings}\n{code}"

    @property
    def cache_key(self) -> str:
        """
        Hash QL code, and return its digest as hexadecimal string.

        The default query runner uses this as cache key.
        """
        # important: do not use 'self._input_code'.
        # that way the timeout and maxsize settings don't affect the digest
        return hashlib.sha256(self.code.encode("utf-8")).hexdigest()

    @property
    def done(self) -> bool:
        """Returns ``True`` if the result set was received."""
        return self.result_set is not None

    @property
    def query_duration_secs(self) -> float:
        """
        How long it took to fetch the result set in seconds.

        This is the duration starting with the API request, and ending once
        the result is written to this query object. Although it depends on how busy
        the API instance is, this can give some indication of how long a query takes.
        """
        return max(0.0, self._time_end_try - self._time_start_try)

    @property
    def run_duration_secs(self) -> float:
        """
        The total required time for this query in seconds (so far).
        """
        if self._time_end_try > 0.0:
            end = self._time_end_try
        else:
            end = asyncio.get_event_loop().time()
        return end - self._time_start

    @property
    def api_version(self) -> Optional[str]:
        """
        The Overpass API version used by the queried instance,
        f.e. ``Overpass API 0.7.56.8 7d656e78``.

        References:
            - https://wiki.openstreetmap.org/wiki/Overpass_API/versions
        """
        if not self.result_set:
            return None

        return self.result_set["generator"]

    @property
    def timestamp_osm(self) -> Optional[str]:
        """
        All OSM edits that have been uploaded before this date are included.

        The format is ``YYYY-MM-DDThh:mm:ssZ``.
        """
        if not self.result_set:
            return None

        return self.result_set["osm3s"]["timestamp_osm_base"]

    @property
    def timestamp_areas(self) -> Optional[str]:
        """
        If the query involves area data processing, this is the date of the latest edit
        that has been considered in the most recent batch run of the area generation.

        The format is ``YYYY-MM-DDThh:mm:ssZ``.
        """
        if not self.result_set:
            return None

        return self.result_set["osm3s"].get("timestamp_areas_base")

    @property
    def copyright(self) -> str:
        """A copyright notice that comes with the result set."""
        if not self.result_set:
            return _COPYRIGHT

        return self.result_set["osm3s"].get("copyright") or _COPYRIGHT

    def __str__(self) -> str:
        if self.kwargs:
            query = f"query {self.kwargs}"
        else:
            query = "query <no kwargs>"

        size = self.result_size_mb
        time_query = self.query_duration_secs
        time_total = self.run_duration_secs

        if self.nb_tries == 0:
            details = "pending"
        elif self.done:
            if self.nb_tries == 1:
                details = f"{size}mb in {time_query:.01f}s"
            else:
                details = f"{size}mb in {time_query:.01f} ({time_total:.01f})s"
        else:
            details = f"failing after {self.nb_tries} tries, {time_total:.01f}s"

        return f"{query} ({details})"

    def __repr__(self) -> str:
        cls_name = type(self).__name__

        details = {
            "kwargs": self._kwargs,
            "done": self.done,
        }

        if self.nb_tries == 0 or self.error:
            details["tries"] = self.nb_tries

        if self.error:
            details["error"] = type(self.error).__name__

        if self.done:
            details["result_size"] = f"{self.result_size_mb}mb"

            if self.nb_tries != 1:
                details["query_duration"] = f"{self.query_duration_secs}s"

        if self.nb_tries > 0:
            details["run_duration"] = f"{self.run_duration_secs}s"

        details_str = ", ".join((f"{k}={v!r}" for k, v in details.items()))

        return f"{cls_name}({details_str})"


QueryRunner = Callable[[Query], Awaitable[None]]
"""
A query runner is async function that is called before a client makes an API request.

Query runners can be used to
 - retry queries when they fail
 - modify queries, f.e. to lower/increase their maxsize/timeout
 - log query results & errors
 - implement caching
"""


class DefaultQueryRunner(QueryRunner):
    """
    A general query runner that
        - retries with an increasing back-off period in between tries if the server is too busy
        - retries and doubles timeout and maxsize settings if they were exceeded
        - limits the number of tries
        - caches query results (useful when debugging)

    This runner does *not*
        - limit the total time a query runs, including retries
        - lower timeout and maxsize settings if the server rejected a query

    Args:
        max_tries: The maximum number of times a query is tried. (5 by default)
        cache_dir: If set, JSON result sets will be cached in this directory.
    """

    def __init__(self, max_tries: int = 5, cache_dir: Optional[Path] = None) -> None:
        self._max_tries = max_tries
        self._cache_dir = cache_dir

    def _cache_read(self, query: Query) -> None:
        if not self._cache_dir or not self._cache_dir.is_dir():
            return

        file_path = self._cache_dir / query.cache_key

        try:
            with open(file_path) as file:
                query._result_set = json.load(file)
        except (OSError, json.JSONDecodeError) as err:
            _logger.error(f"failed to read cached {query}", exc_info=err)

    def _cache_write(self, query: Query) -> None:
        if not self._cache_dir or not self._cache_dir.is_dir():
            return

        file_path = self._cache_dir / query.cache_key

        try:
            with open(file_path, "w") as file:
                json.dump(query.result_set, file)
        except OSError as err:
            _logger.error(f"failed to cache {query}", exc_info=err)

    async def __call__(self, query: Query) -> None:
        # Check cache ahead of first try
        if query.nb_tries == 0:
            self._cache_read(query)

        # Success or cached
        if query.done:
            self._cache_write(query)
            return

        err = query.error

        # Exhausted all tries; do not retry.
        if query.nb_tries == self._max_tries:
            raise err

        # Response errors usually indicate a bug in the client; do not retry.
        if isinstance(err, ResponseError):
            raise err

        # QL error; do not retry.
        if isinstance(err, QueryLanguageError):
            raise err

        if isinstance(err, QueryRejectError):
            # Wait if the server is too busy.
            if err.cause == QueryRejectCause.TOO_BUSY:
                backoff = _backoff_secs(query.nb_tries)
                _logger.debug(f"retry {query} in {backoff:.1f}s")
                await asyncio.sleep(backoff)

            # Wait until a slot opens if the rate limit was exceeded.
            elif err.cause == QueryRejectCause.TOO_MANY_QUERIES:
                return  # let client enforce cooldown

            # Double timeout if exceeded.
            elif err.cause == QueryRejectCause.EXCEEDED_TIMEOUT:
                query.timeout_secs = max(query.timeout_secs * 2, DEFAULT_TIMEOUT)

            # Double maxsize if exceeded.
            elif err.cause == QueryRejectCause.EXCEEDED_MAXSIZE:
                query.maxsize_mb = max(query.maxsize_mb * 2, DEFAULT_MAXSIZE)


def _backoff_secs(tries: int) -> float:
    """Fibonacci sequence: 1, 2, 3, 5, 8, etc."""
    a, b = 1.0, 2.0

    for _ in range(tries):
        a, b = b, a + b

    return a


_logger = logging.getLogger("aio-overpass")
