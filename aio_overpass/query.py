"""Query state and runner."""

import asyncio
import hashlib
import json
import logging
import math
import re
import tempfile
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from aio_overpass._clock import Instant, sleep
from aio_overpass._env import FORCE_DISABLE_CACHE
from aio_overpass.error import (
    ClientError,
    QueryRejectCause,
    is_exceeding_timeout,
    is_rejection,
    is_server_error,
)


__docformat__ = "google"
__all__ = (
    "Query",
    "QueryRunner",
    "DefaultQueryRunner",
    "RequestTimeout",
    "DEFAULT_MAXSIZE_MIB",
    "DEFAULT_TIMEOUT_SECS",
)


DEFAULT_MAXSIZE_MIB: Final[int] = 512
"""Default ``maxsize`` setting in mebibytes."""

DEFAULT_TIMEOUT_SECS: Final[int] = 180
"""Default ``timeout`` setting in seconds."""

_COPYRIGHT: Final[str] = (
    "The data included in this document is from www.openstreetmap.org."
    " The data is made available under ODbL."
)
"""This is the same copyright notice included in result sets"""

_SETTING_PATTERN: Final[re.Pattern[str]] = re.compile(r"\[(\w+?):(.+?)]\s*;?")
"""A pattern to match setting declarations (not the entire settings statement)."""

_NULL_LOGGER: Final[logging.Logger] = logging.getLogger()
_NULL_LOGGER.addHandler(logging.NullHandler())


class Query:
    """
    State of a query that is either pending, running, successful, or failed.

    Args:
        input_code: The input Overpass QL code. Note that some settings might be changed
                    by query runners, notably the 'timeout' and 'maxsize' settings.
        logger: The logger to use for all logging output related to this query.
        **kwargs: Additional keyword arguments that can be used to identify queries.

    References:
        - https://wiki.openstreetmap.org/wiki/Overpass_API/Overpass_QL
    """

    __slots__ = (
        "_error",
        "_input_code",
        "_kwargs",
        "_logger",
        "_max_timed_out_after_secs",
        "_nb_tries",
        "_request_timeout",
        "_response",
        "_response_bytes",
        "_run_lock",
        "_run_timeout_secs",
        "_settings",
        "_time_end_try",
        "_time_start",
        "_time_start_req",
        "_time_start_try",
    )

    def __init__(
        self,
        input_code: str,
        logger: logging.Logger = _NULL_LOGGER,
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        self._run_lock: Final[threading.Lock] = threading.Lock()
        """a lock used to ensure a query cannot be run more than once at the same time"""

        self._input_code: Final[str] = input_code
        """the original given overpass ql code"""

        self._logger: Final[logging.Logger] = logger
        """logger to use for this query"""

        self._kwargs: Final[dict] = kwargs
        """used to identify this query"""

        self._settings = dict(_SETTING_PATTERN.findall(input_code))
        """all overpass ql settings [k:v];"""

        if "out" in self._settings and self._settings["out"] != "json":
            msg = "the '[out:*]' setting is implicitly set to 'json' and should be omitted"
            raise ValueError(msg)

        self._settings["out"] = "json"

        if "maxsize" not in self._settings:
            self._settings["maxsize"] = DEFAULT_MAXSIZE_MIB * 1024 * 1024
        elif not self._settings["maxsize"].isdigit() or int(self._settings["maxsize"]) <= 0:
            msg = "the '[maxsize:*]' setting must be an integer > 0"
            raise ValueError(msg)

        if "timeout" not in self._settings:
            self._settings["timeout"] = DEFAULT_TIMEOUT_SECS
        elif not self._settings["timeout"].isdigit() or int(self._settings["timeout"]) <= 0:
            msg = "the '[timeout:*]' setting must be an integer > 0"
            raise ValueError(msg)

        self._run_timeout_secs: float | None = None
        """total time limit for running this query"""

        self._request_timeout: RequestTimeout = RequestTimeout()
        """config for request timeouts"""

        self._error: ClientError | None = None
        """error of the last try, or None"""

        self._response: dict | None = None
        """response JSON as a dict, or None"""

        self._response_bytes = 0.0
        """number of bytes in a response, or zero"""

        self._nb_tries = 0
        """number of tries so far, starting at zero"""

        self._time_start: Instant | None = None
        """time prior to executing the first try"""

        self._time_start_try: Instant | None = None
        """time prior to executing the most recent try"""

        self._time_start_req: Instant | None = None
        """time prior to executing the most recent try's query request"""

        self._time_end_try: Instant | None = None
        """time the most recent try finished"""

        self._max_timed_out_after_secs: int | None = None
        """maximum of seconds after which the query was cancelled"""

    def reset(self) -> None:
        """Reset the query to its initial state, ignoring previous tries."""
        Query.__init__(
            self,
            input_code=self._input_code,
            logger=self._logger,
            **self._kwargs,
        )

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
    def logger(self) -> logging.Logger:
        """The logger used for logging output related to this query."""
        return self._logger

    @property
    def nb_tries(self) -> int:
        """Current number of tries."""
        return self._nb_tries

    @property
    def error(self) -> ClientError | None:
        """
        Error of the most recent try.

        Returns:
            an error or ``None`` if the query wasn't tried or hasn't failed
        """
        return self._error

    @property
    def response(self) -> dict | None:
        """
        The entire JSON response of the query.

        Returns:
            the response, or ``None`` if the query has not successfully finished (yet)
        """
        return self._response

    @property
    def was_cached(self) -> bool | None:
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
    def result_set(self) -> list[dict] | None:
        """
        The result set of the query.

        This is open data, licensed under the Open Data Commons Open Database License (ODbL).
        You are free to copy, distribute, transmit and adapt this data, as long as you credit
        OpenStreetMap and its contributors. If you alter or build upon this data, you may
        distribute the result only under the same licence.

        Returns:
            the elements of the result set, or ``None`` if the query has not successfully
            finished (yet)

        References:
            - https://www.openstreetmap.org/copyright
            - https://opendatacommons.org/licenses/odbl/1-0/
        """
        if not self._response:
            return None
        return self._response["elements"]

    @property
    def response_size_mib(self) -> float | None:
        """
        The size of the response in mebibytes.

        Returns:
            the size, or ``None`` if the query has not successfully finished (yet)
        """
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
        if not math.isfinite(value) or value <= 0.0:
            msg = "'maxsize_mib' must be finite > 0"
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
    def run_timeout_secs(self) -> float | None:
        """
        A limit to ``run_duration_secs``, that cancels running the query when exceeded.

        Defaults to no timeout.

        The client will raise a ``GiveupError`` if the timeout is reached.

        Not to be confused with ``timeout_secs``, which is a setting for the Overpass API instance,
        that limits a single query execution time. Instead, this value can be used to limit the
        total client-side time spent on this query (see ``Client.run_query``).
        """
        return self._run_timeout_secs

    @run_timeout_secs.setter
    def run_timeout_secs(self, value: float | None) -> None:
        if value is not None and (not math.isfinite(value) or value <= 0.0):
            msg = "'run_timeout_secs' must be finite > 0"
            raise ValueError(msg)
        self._run_timeout_secs = value

    @property
    def run_timeout_elapsed(self) -> bool:
        """Returns ``True`` if ``run_timeout_secs`` is set and has elapsed."""
        return (
            self.run_timeout_secs is not None
            and self.run_duration_secs is not None
            and self.run_timeout_secs < self.run_duration_secs
        )

    @property
    def request_timeout(self) -> "RequestTimeout":
        """Request timeout settings for this query."""
        return self._request_timeout

    @request_timeout.setter
    def request_timeout(self, value: "RequestTimeout") -> None:
        self._request_timeout = value

    def _code(self, next_timeout_secs_used: int) -> str:
        """The query's QL code, substituting the [timeout:*] setting with the given duration."""
        settings_copy = self._settings.copy()
        settings_copy["timeout"] = next_timeout_secs_used

        # remove the original settings statement
        code = _SETTING_PATTERN.sub("", self._input_code)

        # put the adjusted settings in front
        settings = "".join((f"[{k}:{v}]" for k, v in settings_copy.items())) + ";"

        return f"{settings}\n{code}"

    @property
    def cache_key(self) -> str:
        """
        Hash QL code, and return its digest as hexadecimal string.

        The default query runner uses this as cache key.
        """
        # Remove the original settings statement
        code = _SETTING_PATTERN.sub("", self._input_code)
        hasher = hashlib.blake2b(digest_size=8)
        hasher.update(code.encode("utf-8"))
        return hasher.hexdigest()

    @property
    def done(self) -> bool:
        """Returns ``True`` if the result set was received."""
        return self._response is not None

    @property
    def request_duration_secs(self) -> float | None:
        """
        How long it took to fetch the result set in seconds.

        This is the duration starting with the API request, and ending once
        the result is written to this query object. Although it depends on how busy
        the API instance is, this can give some indication of how long a query takes.

        Returns:
            the duration or ``None`` if there is no result set yet, or when it was cached.
        """
        if self._response is None or self.was_cached:
            return None

        assert self._time_end_try is not None
        assert self._time_start_req is not None

        return self._time_end_try - self._time_start_req

    @property
    def run_duration_secs(self) -> float | None:
        """
        The total required time for this query in seconds (so far).

        Returns:
            the duration or ``None`` if there is no result set yet, or when it was cached.
        """
        if self._time_start is None:
            return None

        if self._time_end_try:
            return self._time_end_try - self._time_start

        return self._time_start.elapsed_secs_since

    @property
    def _run_duration_left_secs(self) -> float | None:
        """If a limit was set, returns the seconds until the time to run the query has elapsed."""
        if (time_max := self.run_timeout_secs) and (time_so_far := self.run_duration_secs):
            return max(0, math.ceil(time_max - time_so_far))
        return None

    @property
    def api_version(self) -> str | None:
        """
        The Overpass API version used by the queried instance.

        Returns:
            f.e. ``"Overpass API 0.7.56.8 7d656e78"``, or ``None`` if the query
            has not successfully finished (yet)

        References:
            - https://wiki.openstreetmap.org/wiki/Overpass_API/versions
        """
        if self._response is None:
            return None

        return self._response["generator"]

    @property
    def timestamp_osm(self) -> datetime | None:
        """
        All OSM edits that have been uploaded before this date are included.

        It can take a couple of minutes for changes to the database to show up in the
        Overpass API query results.

        Returns:
            the timestamp, or ``None`` if the query has not successfully finished (yet)
        """
        if self._response is None:
            return None

        date_str = self._response["osm3s"]["timestamp_osm_base"]
        return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ").astimezone(UTC)

    @property
    def timestamp_areas(self) -> datetime | None:
        """
        All area data edits that have been uploaded before this date are included.

        If the query involves area data processing, this is the date of the latest edit
        that has been considered in the most recent batch run of the area generation.

        Returns:
            the timestamp, or ``None`` if the query has not successfully finished (yet), or
            if it does not involve area data processing.
        """
        if self._response is None:
            return None

        date_str = self._response["osm3s"].get("timestamp_areas_base")
        if not date_str:
            return None

        return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ").astimezone(UTC)

    @property
    def copyright(self) -> str:
        """A copyright notice that comes with the result set."""
        if self._response is None:
            return _COPYRIGHT

        return self._response["osm3s"].get("copyright") or _COPYRIGHT

    def __str__(self) -> str:
        query = f"query{self.kwargs!r}"

        size = self.response_size_mib
        time_request = self.request_duration_secs
        time_total = self.run_duration_secs

        if self.nb_tries == 0:
            details = "pending"
        elif self.done:
            if self.nb_tries == 1:
                details = f"done - {size:.01f}mb in {time_request:.01f}s"
            else:
                details = f"done after {time_total:.01f}s - {size:.01f}mb in {time_request:.01f}s"
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
            details["response_size"] = f"{self.response_size_mib:.02f}mb"

            if not self.was_cached:
                details["request_duration"] = f"{self.request_duration_secs:.02f}s"

        if self.nb_tries > 0:
            details["run_duration"] = f"{self.run_duration_secs:.02f}s"

        details_str = ", ".join((f"{k}={v!r}" for k, v in details.items()))

        return f"{cls_name}({details_str})"

    def _begin_try(self) -> None:
        """First thing to call when starting the next try, after invoking the query runner."""
        if self._time_start is None:
            self._time_start = Instant.now()

        self._time_start_try = Instant.now()
        self._time_start_req = None
        self._time_end_try = None

    def _begin_request(self) -> None:
        """Call before making the API call of a try, after waiting for cooldown."""
        self._time_start_req = Instant.now()

    def _succeed_try(self, response: dict, response_bytes: int) -> None:
        """Call when the API call of a try was successful."""
        self._time_end_try = Instant.now()
        self._response = response
        self._response_bytes = response_bytes
        self._error = None

    def _fail_try(self, err: ClientError) -> None:
        """Call when the API call of a try failed."""
        self._error = err

        if is_exceeding_timeout(err):
            self._max_timed_out_after_secs = err.timed_out_after_secs

    def _end_try(self) -> None:
        """Final call in a try."""
        self._nb_tries += 1


@dataclass(kw_only=True, slots=True)
class RequestTimeout:
    """
    Request timeout settings.

    Attributes:
        total_without_query_secs: If set, the sum of this duration and the query's ``[timeout:*]``
                                  setting is used as timeout duration of the entire request,
                                  including connection establishment, request sending and response
                                  reading (``aiohttp.ClientTimeout.total``).
                                  Defaults to 20 seconds.
        sock_connect_secs: The maximum number of seconds allowed for pure socket connection
                           establishment (same as ``aiohttp.ClientTimeout.sock_connect``).
        each_sock_read_secs: The maximum number of seconds allowed for the period between reading
                             a new chunk of data (same as ``aiohttp.ClientTimeout.sock_read``).
    """

    total_without_query_secs: float | None = 20.0
    sock_connect_secs: float | None = None
    each_sock_read_secs: float | None = None

    def __post_init__(self) -> None:
        if self.total_without_query_secs is not None and (
            not math.isfinite(self.total_without_query_secs) or self.total_without_query_secs <= 0.0
        ):
            msg = "'total_without_query_secs' must be finite > 0"
            raise ValueError(msg)

        if self.sock_connect_secs is not None and (
            not math.isfinite(self.sock_connect_secs) or self.sock_connect_secs <= 0.0
        ):
            msg = "'sock_connect_secs' must be finite > 0"
            raise ValueError(msg)

        if self.each_sock_read_secs is not None and (
            not math.isfinite(self.each_sock_read_secs) or self.each_sock_read_secs <= 0.0
        ):
            msg = "'each_sock_read_secs' must be finite > 0"
            raise ValueError(msg)


class QueryRunner(ABC):
    """
    A query runner is an async function that is called before a client makes an API request.

    Query runners can be used to…
     - …retry queries when they fail
     - …modify queries, f.e. to lower/increase their maxsize/timeout
     - …log query results & errors
     - …implement caching

    The absolute minimum a query runner function has to do is to simply return to (re)try
    a query, or to raise ``query.error`` to stop trying.
    """

    __slots__ = ()

    @abstractmethod
    async def __call__(self, query: Query) -> None:
        """Called with the current query state before the client makes an API request."""


class DefaultQueryRunner(QueryRunner):
    """
    The default query runner.

    This runner…
     - …retries with an increasing back-off period in between tries if the server is too busy
     - …retries and doubles timeout and maxsize settings if they were exceeded
     - …limits the number of tries
     - …optionally caches query results in temp files

    This runner does *not* lower timeout and maxsize settings if the server rejected a query.

    Args:
        max_tries: The maximum number of times a query is tried. (5 by default)
        cache_ttl_secs: Amount of seconds a query's result set is cached for.
                        Set to zero to disable caching. (zero by default)
    """

    __slots__ = (
        "_cache_ttl_secs",
        "_max_tries",
    )

    def __init__(self, max_tries: int = 5, cache_ttl_secs: int = 0) -> None:
        if max_tries < 1:
            msg = "max_tries must be >= 1"
            raise ValueError(msg)

        if cache_ttl_secs < 0:
            msg = "cache_ttl_secs must be >= 0"
            raise ValueError(msg)

        self._max_tries = max_tries
        self._cache_ttl_secs = cache_ttl_secs

    def _is_caching(self, query: Query) -> bool:
        if self._cache_ttl_secs and FORCE_DISABLE_CACHE:
            query.logger.debug("caching is forced disabled")
            return False
        return self._cache_ttl_secs > 0

    @staticmethod
    def _cache_file_name(query: Query) -> str:
        return f"{query.cache_key}.json"

    @staticmethod
    def _cache_file_path(query: Query) -> Path:
        return Path(tempfile.gettempdir()) / DefaultQueryRunner._cache_file_name(query)

    @staticmethod
    def _cache_read(query: Query) -> None:
        logger = query.logger

        now = int(time.time())

        file_path = DefaultQueryRunner._cache_file_path(query)

        if not file_path.exists():
            logger.info("result was not cached")
            logger.debug(f"checked for cache at {file_path}")
            return

        try:
            with Path(file_path).open(encoding="utf-8") as file:
                response = json.load(file)
        except (OSError, json.JSONDecodeError):
            logger.exception(f"failed to read cached {query}")
            return

        if response.get(_EXPIRATION_KEY, 0) <= now:
            logger.info(f"{query} cache expired")
            return

        query._response = response
        logger.info(f"{query} was cached")

    def _cache_write(self, query: Query) -> None:
        logger = query.logger

        now = int(time.time())

        assert query._response is not None
        query._response[_EXPIRATION_KEY] = now + self._cache_ttl_secs

        file_path = DefaultQueryRunner._cache_file_path(query)

        logger.debug(f"caching at {file_path}…")

        try:
            with Path(file_path).open(mode="w", encoding="utf-8") as file:
                json.dump(query._response, file)
        except OSError:
            logger.exception(f"failed to cache {query}")

    @staticmethod
    def cache_delete(query: Query) -> None:
        """Clear a cached response for the given query by removing the file on disk."""
        file_path = DefaultQueryRunner._cache_file_path(query)
        file_path.unlink(missing_ok=True)

    @staticmethod
    def _cache_expire(query: Query) -> None:
        """
        Clear a cached response for the given query by marking it expired in the file on disk.

        This should only be used for testing.
        """
        file_path = DefaultQueryRunner._cache_file_path(query)

        with Path(file_path).open(encoding="utf-8") as file:
            response = json.load(file)

        response[_EXPIRATION_KEY] = 0

        with Path(file_path).open(mode="w", encoding="utf-8") as file:
            json.dump(response, file)

    async def __call__(self, query: Query) -> None:  # noqa: C901
        """Called with the current query state before the client makes an API request."""
        logger = query.logger

        # Check cache ahead of first try
        if query.nb_tries == 0 and self._is_caching(query):
            await asyncio.to_thread(DefaultQueryRunner._cache_read, query)

        # Success or cached
        if query.done:
            logger.info(f"{query}")
            if not query.was_cached and self._is_caching(query):
                await asyncio.to_thread(self._cache_write, query)
            return

        err = query.error

        if err:
            logger.info(f"try for query{query.kwargs!r} failed: {err}")

        if is_server_error(err):
            logger.error(f"unexpected response body:\n{err.body}")

        # Do not retry if we exhausted all tries, when a retry would not change the result,
        # or when the timeout was reached.
        if err and (query.nb_tries == self._max_tries or not err.should_retry):
            logger.error(f"give up on {query}", exc_info=err)
            raise err

        if is_rejection(err):
            # Wait if the server is too busy.
            if err.cause == QueryRejectCause.TOO_BUSY:
                backoff = _fibo_backoff_secs(query.nb_tries)
                logger.info(f"retry {query} in {backoff:.1f}s")
                await sleep(backoff)

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


def _fibo_backoff_secs(tries: int) -> float:
    """Fibonacci sequence without zero: 1, 1, 2, 3, 5, 8, etc."""
    a, b = 1.0, 1.0

    for _ in range(tries):
        a, b = b, a + b

    return a


_EXPIRATION_KEY: Final[str] = "__expiration__"
