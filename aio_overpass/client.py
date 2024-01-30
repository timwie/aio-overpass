"""Interface for making API calls."""

import asyncio
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from urllib.parse import urljoin

from aio_overpass import __version__
from aio_overpass.error import (
    CallError,
    CallTimeoutError,
    ClientError,
    GiveupError,
    RunnerError,
    _raise_for_request_error,
    _raise_for_response,
    _result_or_raise,
    is_too_many_queries,
)
from aio_overpass.query import DefaultQueryRunner, Query, QueryRunner

import aiohttp
from aiohttp import ClientTimeout


__docformat__ = "google"
__all__ = (
    "Client",
    "Status",
    "DEFAULT_INSTANCE",
    "DEFAULT_USER_AGENT",
)


DEFAULT_INSTANCE = "https://overpass-api.de/api/"
"""Main Overpass API instance."""

DEFAULT_USER_AGENT = f"aio-overpass/{__version__} (https://github.com/timwie/aio-overpass)"
"""User agent that points to the ``aio-overpass`` repo."""


@dataclass(kw_only=True, slots=True)
class Status:
    """
    Information about the API server's rate limit.

    Attributes:
        slots: The maximum number of concurrent queries per IP
               (or ``None`` if there is no rate limit).
        free_slots: The number of slots open for this IP
                    (or ``None`` if there is no rate limit).
        cooldown_secs: The number of seconds until a slot opens for this IP
                       (or 0 if there is a free slot).
        endpoint: Announced endpoint. For example, there are two distinct servers
                  that both can be reached by the main Overpass API instance.
                  Depending on server load, a query may be sent to either of them.
                  This value is the server name, f.e. ``"gall.openstreetmap.de/"``.
        nb_running_queries: Number of currently running queries for this IP.
    """

    slots: int | None
    free_slots: int | None
    cooldown_secs: int
    endpoint: str | None
    nb_running_queries: int

    def __repr__(self) -> str:
        f, s, c = self.free_slots, self.slots, self.cooldown_secs

        if self.slots:
            return f"{type(self).__name__}(slots={f}/{s}, cooldown={c}s)"

        return f"{type(self).__name__}(slots=∞, cooldown={c}s)"


class Client:
    """
    A client for the Overpass API.

    Requests are rate-limited according to the configured number of slots per IP for the specified
    API server. By default, queries are retried whenever the server is too busy, or the rate limit
    was exceeded. Custom query runners can be used to implement your own retry strategy.

    Args:
        url: The url of an Overpass API instance. Defaults to the main Overpass API instance.
        user_agent: A string used for the User-Agent header. It is good practice to provide a string
                    that identifies your application, and includes a way to contact you (f.e. an
                    e-mail, or a link to a repository). This is important if you make too many
                    requests, or queries that require a lot of resources.
        concurrency: The maximum number of simultaneous connections. In practice the amount
                     of concurrent queries may be limited by the number of slots it provides for
                     each IP.
        status_timeout_secs: If set, status requests to the Overpass API will time out after
                             this duration in seconds. Defaults to no timeout.
        runner: You can provide another query runner if you want to implement your own retry
                strategy.

    References:
        - https://wiki.openstreetmap.org/wiki/Overpass_API#Public_Overpass_API_instances
    """

    __slots__ = (
        "_concurrency",
        "_maybe_session",
        "_runner",
        "_status_timeout_secs",
        "_url",
        "_user_agent",
    )

    def __init__(  # noqa: PLR0913
        self,
        url: str = DEFAULT_INSTANCE,
        user_agent: str = DEFAULT_USER_AGENT,
        concurrency: int = 32,
        status_timeout_secs: float | None = None,
        runner: QueryRunner | None = None,
    ) -> None:
        if concurrency <= 0:
            msg = "'concurrency' must be > 0"
            raise ValueError(msg)
        if status_timeout_secs is not None and status_timeout_secs <= 0.0:
            msg = "'status_timeout_secs' must be > 0"
            raise ValueError(msg)

        self._url = url
        self._user_agent = user_agent
        self._concurrency = concurrency
        self._status_timeout_secs = status_timeout_secs
        self._runner = runner or DefaultQueryRunner()

        self._maybe_session: aiohttp.ClientSession | None = None

    def _session(self) -> aiohttp.ClientSession:
        """The session used for all requests of this client."""
        if not self._maybe_session or self._maybe_session.closed:
            headers = {"User-Agent": self._user_agent}
            connector = aiohttp.TCPConnector(limit=self._concurrency)
            self._maybe_session = aiohttp.ClientSession(headers=headers, connector=connector)

        return self._maybe_session

    async def close(self) -> None:
        """Cancel all running queries and close the underlying session."""
        if self._maybe_session and not self._maybe_session.closed:
            # do not care if this fails
            with suppress(CallError):
                _ = await self.cancel_queries()

            # is raised when there are still active queries. that's ok
            with suppress(aiohttp.ServerDisconnectedError):
                await self._maybe_session.close()

    async def _status(self, timeout: ClientTimeout | None = None) -> "Status":
        endpoint = urljoin(self._url, "status")
        timeout = timeout or aiohttp.ClientTimeout(total=self._status_timeout_secs)
        async with _map_request_error(timeout), self._session().get(
            url=endpoint, timeout=timeout
        ) as response:
            return await _parse_status(response)

    async def status(self) -> Status:
        """
        Check the current API status.

        The timeout of this request is configured with the ``status_timeout_secs`` argument.

        Raises:
            ClientError: if the status could not be looked up
        """
        return await self._status()

    async def cancel_queries(self, timeout_secs: float | None = None) -> int:
        """
        Cancel all running queries.

        This can be used to terminate runaway queries that prevent you from sending new ones.

        Returns:
            the number of terminated queries

        Raises:
            ClientError: if the request to cancel queries failed
        """
        timeout = aiohttp.ClientTimeout(total=timeout_secs) if timeout_secs else None
        headers = {"User-Agent": self._user_agent}
        endpoint = urljoin(self._url, "kill_my_queries")

        # use a new session here to get around our concurrency limit
        async with aiohttp.ClientSession(headers=headers) as session, _map_request_error(
            timeout
        ), session.get(endpoint, timeout=timeout) as response:
            body = await response.text()
            killed_pids = re.findall("\\(pid (\\d+)\\)", body)
            return len(set(killed_pids))

    async def run_query(self, query: Query, raise_on_failure: bool = True) -> None:
        """
        Send a query to the API, and await its completion.

        "Running" the query entails acquiring a connection from the pool, the query requests
        themselves (which may be retried), status requests when the server is busy,
        and cooldown periods.

        The query runner is invoked before every try, and once after the last try.

        To run multiple queries concurrently, wrap the returned coroutines in an ``asyncio`` task,
        f.e. with ``asyncio.create_task()`` and subsequent ``asyncio.gather()``.

        Args:
            query: the query to run on this API instance
            raise_on_failure: if ``True``, raises ``query.error`` if the query failed

        Raises:
            ClientError: when query or status requests fail. If the query was retried, the error
                         of the last try will be raised. The same exception is also captured in
                         ``query.error``. Raising can be prevented by setting ``raise_on_failure``
                         to ``False``.
            RunnerError: when a call to the query runner raises. This exception is raised
                         even if ``raise_on_failure` is ``False``, since it is likely an error
                         that is not just specific to this query.
        """
        if query.done:
            return  # nothing to do

        if query.nb_tries > 0:
            query.reset()  # reset failed queries

        # query runner is invoked before every try, and once after the last try
        while True:
            await self._invoke_runner(query, raise_on_failure=raise_on_failure)
            if query.done:
                return
            await self._try_query_once(query)

    async def _invoke_runner(self, query: Query, raise_on_failure: bool) -> None:
        """
        Invoke the query runner.

        Raises:
            ClientError: if the runner raises ``query.error``
            ValueError: if the runner raises a different ``ClientError`` than ``query.error``
            RunnerError: if the runner raises any other exception (which it shouldn't)
        """
        try:
            await self._runner(query)
        except ClientError as err:
            if err is not query.error:
                msg = "query runner raised a ClientError other than 'query.error'"
                raise ValueError(msg) from err
            if raise_on_failure:
                raise
        except AssertionError:
            raise
        except BaseException as err:
            raise RunnerError(cause=err) from err

    async def _try_query_once(self, query: Query) -> None:
        """A single iteration of running a query."""
        query_mut = query._mutator()
        query_mut.begin_try()

        try:
            await self._cooldown(query)

            req_timeout = _next_query_req_timeout(query)

            if req_timeout.total and req_timeout.total <= 0.0:
                assert query.run_duration_secs
                raise GiveupError(kwargs=query.kwargs, after_secs=query.run_duration_secs)

            query_mut.begin_request()

            query.logger.info(f"call api for {query}")

            async with _map_request_error(req_timeout), self._session().post(
                url=urljoin(self._url, "interpreter"),
                data=query._code(),
                timeout=req_timeout,
            ) as response:
                query_mut.succeed_try(
                    response=await _result_or_raise(response, query.kwargs),
                    response_bytes=response.content.total_bytes,
                )

        except CallTimeoutError as err:
            fail_with: ClientError = err
            if query.run_timeout_elapsed:
                assert query.run_duration_secs is not None
                fail_with = GiveupError(kwargs=query.kwargs, after_secs=query.run_duration_secs)
            query_mut.fail_try(fail_with)

        except ClientError as err:
            query_mut.fail_try(err)

        finally:
            query_mut.end_try()

    async def _cooldown(self, query: Query) -> None:
        """
        If the given query failed with ``TOO_MANY_QUERIES``, check for a cooldown period.

        Raises:
            ClientError: if the status request to find out the cooldown period fails
            GiveupError: if the cooldown is longer than the remaining run duration
        """
        logger = query.logger

        if not is_too_many_queries(query.error):
            return

        # If this client is running too many queries, we can check the status for a
        # cooldown period. This request failing is a bit of an edge case.
        # 'query.error' will be overwritten, which means we will not check for a
        # cooldown in the next iteration.
        status = await self._status(timeout=self._next_status_req_timeout(query))

        if not status.cooldown_secs:
            return

        run_duration = query.run_duration_secs
        assert run_duration

        if run_timeout := query.run_timeout_secs:
            remaining = run_timeout - run_duration

            if status.cooldown_secs > remaining:
                logger.error(f"give up on {query} due to {status.cooldown_secs:.1f}s cooldown")
                raise GiveupError(kwargs=query.kwargs, after_secs=run_duration)

        logger.info(f"{query} has cooldown for {status.cooldown_secs:.1f}s")
        await asyncio.sleep(status.cooldown_secs)

    def _next_status_req_timeout(self, query: Query) -> aiohttp.ClientTimeout:
        """Status request timeout; possibly limited by either the run or status timeout settings."""
        remaining = None

        run_duration = query.run_duration_secs
        assert run_duration

        if run_timeout := query.run_timeout_secs:
            remaining = run_timeout - run_duration

            if remaining <= 0.0:
                raise GiveupError(kwargs=query.kwargs, after_secs=run_duration)

            if self._status_timeout_secs:
                remaining = min(remaining, self._status_timeout_secs)  # cap timeout if configured

        return aiohttp.ClientTimeout(total=remaining)


def _next_query_req_timeout(query: Query) -> aiohttp.ClientTimeout:
    """Query request timeout; possibly limited by either the run or request timeout settings."""
    run_total = None  # time left until "run_timeout_secs" exceeded
    query_total = None  # "[timeout:*]" setting plus "total_without_query_secs"

    run_duration = query.run_duration_secs
    assert run_duration

    if run_timeout := query.run_timeout_secs:
        run_total = run_timeout - run_duration

    if add_to_timeout_secs := query.request_timeout.total_without_query_secs:
        query_total = float(query.timeout_secs) + add_to_timeout_secs

    total = min(run_total, query_total) if run_total and query_total else run_total or query_total

    return aiohttp.ClientTimeout(
        total=total,
        connect=None,
        sock_connect=query.request_timeout.sock_connect_secs,
        sock_read=query.request_timeout.each_sock_read_secs,
    )


async def _parse_status(response: aiohttp.ClientResponse) -> Status:
    """Parses an /api/status response."""
    text = await response.text()

    slots: int | None = 0
    free_slots = None
    cooldown_secs = 0
    endpoint = None
    nb_running_queries = 0

    match_slots_overall = re.findall(r"Rate limit: (\d+)", text)
    match_slots_available = re.findall(r"(\d+) slots available now", text)
    match_cooldowns = re.findall(r"Slot available after: .+, in (\d+) seconds", text)
    match_endpoint = re.findall(r"Announced endpoint: (.+)", text)
    match_running_queries = re.findall(r"\d+\t\d+\t\d+\t\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", text)

    try:
        (slots_str,) = match_slots_overall
        slots = int(slots_str) or None

        endpoint = match_endpoint[0] if match_endpoint else None
        endpoint = None if endpoint == "none" else endpoint

        nb_running_queries = len(match_running_queries)

        if slots:
            cooldowns = [int(secs) for secs in match_cooldowns]

            if match_slots_available:
                free_slots_str = match_slots_available[0]
                free_slots = int(free_slots_str)
            else:
                free_slots = slots - len(cooldowns)

            cooldown_secs = 0 if free_slots > 0 else min(cooldowns)
    except ValueError as err:
        await _raise_for_response(response, cause=err)

    return Status(
        slots=slots,
        free_slots=free_slots,
        cooldown_secs=cooldown_secs,
        endpoint=endpoint,
        nb_running_queries=nb_running_queries,
    )


@asynccontextmanager
async def _map_request_error(
    timeout: ClientTimeout | None = None,
) -> AsyncIterator[None]:
    """Context to make requests in; maps errors to our exception types."""
    try:
        yield
    except aiohttp.ClientError as err:
        await _raise_for_request_error(err)
    except asyncio.TimeoutError as err:
        assert timeout is not None and timeout.total
        raise CallTimeoutError(cause=err, after_secs=timeout.total) from err
