"""Query state and runner."""

import asyncio
import hashlib
import json
import logging
import re
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Protocol

from aio_overpass.error import (
    ClientError,
    QueryLanguageError,
    QueryRejectCause,
    QueryRejectError,
    ResponseError,
)


__docformat__ = "google"
__all__ = (
    "Query",
    "QueryRunner",
    "DefaultQueryRunner",
    "DEFAULT_MAXSIZE",
    "DEFAULT_TIMEOUT",
)


DEFAULT_MAXSIZE = 512
"""Default ``maxsize`` setting in mebibytes"""

DEFAULT_TIMEOUT = 180
"""Default ``timeout`` setting in seconds"""

_COPYRIGHT = "The data included in this document is from www.openstreetmap.org. The data is made available under ODbL."  # noqa: E501
"""This is the same copyright notice included in result sets"""

_SETTING_PATTERN = re.compile(r"\[(\w+?):(.+?)]\s*;?")
"""A pattern to match setting declarations (not the entire settings statement)."""


class Query:
    """
    State of a query that is either pending, successful, or failed.

    Args:
        input_code: The input Overpass QL code. Note that some settings might be changed
                    by query runners, notably the 'timeout' and 'maxsize' settings.
        logger: The logger to use for all logging output related to this query.
        **kwargs: Additional keyword arguments that can be used to identify queries.

    References:
        - https://wiki.openstreetmap.org/wiki/Overpass_API/Overpass_QL
    """

    def __init__(self, input_code: str, logger: Optional[logging.Logger] = None, **kwargs) -> None:
        self._input_code = input_code
        self._logger = logger
        self._kwargs = kwargs

        self._settings = dict(_SETTING_PATTERN.findall(input_code))

        self._settings["out"] = "json"

        if "maxsize" not in self._settings:
            self._settings["maxsize"] = DEFAULT_MAXSIZE * 1024 * 1024

        if "timeout" not in self._settings:
            self._settings["timeout"] = DEFAULT_TIMEOUT

        self._client_timeout: Optional[float] = None

        # set by the client that executes this query
        self._error: Optional[ClientError] = None
        self._response: Optional[dict] = None
        self._response_bytes = 0.0
        self._time_end_try = 0.0  # time the most recent try finished
        self._time_start = 0.0  # time prior to executing the first try
        self._time_start_try = 0.0  # time prior to executing the most recent try
        self._nb_tries = 0

    def _has_cooldown(self) -> bool:
        """When ``True``, we should query the API status to retrieve our cooldown period."""
        return (
            isinstance(self.error, QueryRejectError)
            and self.error.cause == QueryRejectCause.TOO_MANY_QUERIES
        )

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
    def logger(self) -> Optional[logging.Logger]:
        """If set, this is the logger used for logging output related to this query."""
        return self._logger

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
    def response(self) -> Optional[dict]:
        """The entire JSON response of the query."""
        return self._response

    @property
    def was_cached(self) -> Optional[bool]:
        """
        Indicates whether the query result was cached.

        Returns:
            ``None`` if the query has not been run yet.
            ``True`` if the query has a result set with zero tries.
            ``False`` otherwise.
        """
        if self._response is None:
            return None
        return self._nb_tries == 0

    @property
    def result_set(self) -> Optional[list[dict]]:
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
        if not self._response:
            return None
        return self._response["elements"]

    @property
    def response_size_mib(self) -> Optional[float]:
        """The size of the response in mebibytes."""
        if self._response is None:
            return None
        return self._response_bytes / 1024.0 / 1024.0

    @property
    def maxsize_mib(self) -> float:
        """
        The current value of the [maxsize:*] setting in mebibytes.

        This size indicates the maximum allowed memory for the query in bytes RAM on the server,
        as expected by the user. If the query needs more RAM than this value, the server may abort
        the query with a memory exhaustion. The higher this size, the more probably the server
        rejects the query before executing it.
        """
        return float(self._settings["maxsize"]) // 1024.0 // 1024.0

    @maxsize_mib.setter
    def maxsize_mib(self, value: float) -> None:
        if value <= 0.0:
            msg = "maxsize_mib must be > 0.0"
            raise ValueError(msg)
        self._settings["maxsize"] = int(value * 1024.0 * 1024.0)

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
        if value < 1:
            msg = "timeout_secs must be >= 1"
            raise ValueError(msg)
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
        if value is not None and value <= 0.0:
            msg = "run_timeout_secs must be > 0"
            raise ValueError(msg)
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
        return self._response is not None

    @property
    def query_duration_secs(self) -> Optional[float]:
        """
        How long it took to fetch the result set in seconds.

        This is the duration starting with the API request, and ending once
        the result is written to this query object. Although it depends on how busy
        the API instance is, this can give some indication of how long a query takes.

        This is ``None`` if there is no result set yet, or when it was cached.
        """
        if self._response is None or self.was_cached:
            return None

        return max(0.0, self._time_end_try - self._time_start_try)

    @property
    def run_duration_secs(self) -> Optional[float]:
        """
        The total required time for this query in seconds (so far).

        This is ``None`` if the query has not been run yet, or when its result was cached.
        """
        if self._time_start == 0.0:
            return None

        end = self._time_end_try if self._time_end_try > 0.0 else asyncio.get_event_loop().time()
        return end - self._time_start

    @property
    def api_version(self) -> Optional[str]:
        """
        The Overpass API version used by the queried instance.

        Returns:
            f.e. ``"Overpass API 0.7.56.8 7d656e78"``.

        References:
            - https://wiki.openstreetmap.org/wiki/Overpass_API/versions
        """
        if self._response is None:
            return None

        return self._response["generator"]

    @property
    def timestamp_osm(self) -> Optional[datetime]:
        """
        All OSM edits that have been uploaded before this date are included.

        It can take a couple of minutes for changes to the database to show up in the
        Overpass API query results.
        """
        if self._response is None:
            return None

        date_str = self._response["osm3s"]["timestamp_osm_base"]
        return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ")

    @property
    def timestamp_areas(self) -> Optional[datetime]:
        """
        All area data edits that have been uploaded before this date are included.

        If the query involves area data processing, this is the date of the latest edit
        that has been considered in the most recent batch run of the area generation.
        Otherwise, it is set to ``None``.
        """
        if self._response is None:
            return None

        date_str = self._response["osm3s"].get("timestamp_areas_base")
        if not date_str:
            return None

        return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ")

    @property
    def copyright(self) -> str:
        """A copyright notice that comes with the result set."""
        if self._response is None:
            return _COPYRIGHT

        return self._response["osm3s"].get("copyright") or _COPYRIGHT

    def __str__(self) -> str:
        query = f"query {self.kwargs}" if self.kwargs else "query <no kwargs>"

        size = self.response_size_mib
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
            t = "try" if self.nb_tries == 1 else "tries"
            details = f"failing after {self.nb_tries} {t}, {time_total:.01f}s"

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
            details["result_size"] = f"{self.response_size_mib:.02f}mb"

            if not self.was_cached:
                details["query_duration"] = f"{self.query_duration_secs:.02f}s"

        if self.nb_tries > 0:
            details["run_duration"] = f"{self.run_duration_secs:.02f}s"

        details_str = ", ".join((f"{k}={v!r}" for k, v in details.items()))

        return f"{cls_name}({details_str})"


class QueryRunner(Protocol):
    """
    A query runner is an async function that is called before a client makes an API request.

    Query runners can be used to
     - retry queries when they fail
     - modify queries, f.e. to lower/increase their maxsize/timeout
     - log query results & errors
     - implement caching
    """

    async def __call__(self, query: Query) -> None:
        """Called with the current query state before the client makes an API request."""
        pass


class DefaultQueryRunner(QueryRunner):
    """
    The default query runner.

    This runner…
     - …retries with an increasing back-off period in between tries if the server is too busy
     - …retries and doubles timeout and maxsize settings if they were exceeded
     - …limits the number of tries
     - …optionally caches query results in temp files

    This runner does *not*…
     - …limit the total time a query runs, including retries
     - …lower timeout and maxsize settings if the server rejected a query

    Args:
        max_tries: The maximum number of times a query is tried. (5 by default)
        cache_ttl_secs: Amount of seconds a query's result set is cached for.
                        Set to zero to disable caching. (zero by default)
    """

    def __init__(self, max_tries: int = 5, cache_ttl_secs: int = 0) -> None:
        if max_tries < 1:
            msg = "max_tries must be >= 1"
            raise ValueError(msg)

        if cache_ttl_secs < 0:
            msg = "cache_ttl_secs must be >= 0"
            raise ValueError(msg)

        self._max_tries = max_tries
        self._cache_ttl_secs = cache_ttl_secs

    @classmethod
    def _logger(cls, query: Query) -> logging.Logger:
        return query.logger or logging.getLogger(f"{cls.__module__}.{cls.__name__}")

    def _cache_read(self, query: Query) -> None:
        logger = DefaultQueryRunner._logger(query)

        if not self._cache_ttl_secs:
            logger.debug("caching is disabled")
            return

        now = int(time.time())

        file_name = f"{query.cache_key}.json"
        file_path = Path(tempfile.gettempdir()) / file_name

        if not file_path.exists():
            logger.info("result was not cached")
            logger.debug(f"checked for cache at {file_path}")
            return

        try:
            with open(file_path) as file:
                response = json.load(file)
        except (OSError, json.JSONDecodeError):
            logger.exception(f"failed to read cached {query}")

        if response.get(_EXPIRATION_KEY, 0) <= now:
            logger.info(f"{query} cache expired")
            return

        query._response = response
        logger.info(f"{query} was cached")

    def _cache_write(self, query: Query) -> None:
        logger = DefaultQueryRunner._logger(query)

        if not self._cache_ttl_secs:
            return

        now = int(time.time())
        query._response[_EXPIRATION_KEY] = now + self._cache_ttl_secs

        file_name = f"{query.cache_key}.json"
        file_path = Path(tempfile.gettempdir()) / file_name

        logger.debug(f"caching at {file_path}…")

        try:
            with open(file_path, "w") as file:
                json.dump(query._response, file)
        except OSError:
            logger.exception(f"failed to cache {query}")

    async def __call__(self, query: Query) -> None:
        """Called with the current query state before the client makes an API request."""
        logger = DefaultQueryRunner._logger(query)

        # Check cache ahead of first try
        if query.nb_tries == 0:
            self._cache_read(query)

        # Success or cached
        if query.done:
            if not query.was_cached:
                self._cache_write(query)
            return

        err = query.error

        # Do not retry if we exhausted all tries, or when a retry would not change the result.
        failed = query.nb_tries == self._max_tries or isinstance(
            err, (ResponseError, QueryLanguageError)
        )

        # Exhausted all tries; do not retry.
        if err and failed:
            logger.error(f"give up on {query}", exc_info=err)
            raise err

        if isinstance(err, QueryRejectError):
            # Wait if the server is too busy.
            if err.cause == QueryRejectCause.TOO_BUSY:
                backoff = _fibo_backoff_secs(query.nb_tries)
                logger.info(f"retry {query} in {backoff:.1f}s")
                await asyncio.sleep(backoff)

            # Wait until a slot opens if the rate limit was exceeded.
            elif err.cause == QueryRejectCause.TOO_MANY_QUERIES:
                pass  # let client enforce cooldown

            # Double timeout if exceeded.
            elif err.cause == QueryRejectCause.EXCEEDED_TIMEOUT:
                old = f"{query.timeout_secs:.1f}s"
                query.timeout_secs *= 2
                new = f"{query.timeout_secs:.1f}s"
                logger.info(f"increased [timeout:*] for {query} from {old} to {new}")

            # Double maxsize if exceeded.
            elif err.cause == QueryRejectCause.EXCEEDED_MAXSIZE:
                old = f"{query.maxsize_mib:.1f}mib"
                query.maxsize_mib *= 2
                new = f"{query.maxsize_mib:.1f}mib"
                logger.info(f"increased [maxsize:*] for {query} from {old} to {new}")


_EXPIRATION_KEY = "__expiration__"


def _fibo_backoff_secs(tries: int) -> float:
    """Fibonacci sequence without zero: 1, 1, 2, 3, 5, 8, etc."""
    a, b = 1.0, 1.0

    for _ in range(tries):
        a, b = b, a + b

    return a


def __cache_delete(query: Query) -> None:
    """Clear a response cached by the default runner (only to be used in tests)."""
    file_name = f"{query.cache_key}.json"
    file_path = Path(tempfile.gettempdir()) / file_name
    file_path.unlink(missing_ok=True)


def __cache_expire(query: Query) -> None:
    """Clear a response cached by the default runner (only to be used in tests)."""
    file_name = f"{query.cache_key}.json"
    file_path = Path(tempfile.gettempdir()) / file_name

    with open(file_path) as file:
        response = json.load(file)

    response[_EXPIRATION_KEY] = 0

    with open(file_path, "w") as file:
        json.dump(response, file)
