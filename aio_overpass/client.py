"""Interface for making API calls."""

import asyncio
import logging
import re
from contextlib import suppress
from dataclasses import dataclass
from typing import Optional, Union
from urllib.parse import urljoin

from aio_overpass import __version__
from aio_overpass.error import (
    CallError,
    CallTimeoutError,
    ClientError,
    GiveupError,
    QueryRejectCause,
    QueryRejectError,
    RunnerError,
    _result_or_raise,
    _to_client_error,
)
from aio_overpass.query import DefaultQueryRunner, Query, QueryRunner

import aiohttp
from aiohttp import ClientTimeout
from aiohttp.helpers import sentinel


__docformat__ = "google"
__all__ = (
    "Client",
    "Status",
    "DEFAULT_INSTANCE",
    "DEFAULT_USER_AGENT",
)


DEFAULT_INSTANCE = "https://overpass-api.de/api/"
DEFAULT_USER_AGENT = f"aio-overpass/{__version__} (https://github.com/timwie/aio-overpass)"


@dataclass
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
        concurrency: Maximum concurrent queries configured for this client.
    """

    slots: Optional[int]
    free_slots: Optional[int]
    cooldown_secs: int
    concurrency: int

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
        concurrency: Affects the maximum number of concurrent queries. Usually, the API server
                     status includes a number of slots it provides for each IP. If that is the
                     case, we pick the minimum of that number of slots and ``concurrency`` as
                     concurrency limit. If the server does not provide a limit itself,
                     ``concurrency`` will be used as concurrency limit.
        runner: You can provide another query runner if you want to implement your own retry
                strategy.

    References:
        - https://wiki.openstreetmap.org/wiki/Overpass_API#Public_Overpass_API_instances
    """

    def __init__(
        self,
        url: str = DEFAULT_INSTANCE,
        user_agent: str = DEFAULT_USER_AGENT,
        concurrency: int = 32,
        runner: Optional[QueryRunner] = None,
    ) -> None:
        if concurrency <= 0:
            msg = "'concurrency' must be > 0"
            raise ValueError(msg)

        self._url = url
        self._user_agent = user_agent
        self._concurrency = concurrency
        self._runner = runner or DefaultQueryRunner()

        self._maybe_session: Optional[aiohttp.ClientSession] = None
        self._maybe_any_status: Optional[Status] = None
        self._maybe_sem: Optional[asyncio.BoundedSemaphore] = None

    def _session(self) -> aiohttp.ClientSession:
        """The session used for all requests of this client."""
        if not self._maybe_session or self._maybe_session.closed:
            headers = {"User-Agent": self._user_agent}
            connector = aiohttp.TCPConnector(limit=0)  # we limit concurrency ourselves
            self._maybe_session = aiohttp.ClientSession(headers=headers, connector=connector)

        return self._maybe_session

    async def _rate_limiter(
        self,
        timeout: Union[ClientTimeout, object] = sentinel,
    ) -> asyncio.BoundedSemaphore:
        """
        A rate-limiting semaphore for queries.

        This semaphore can be acquired as many times as there are query slots at the API instance.
        If all slots are acquired, further queries need to wait until a slot is released.
        """
        status = self._maybe_any_status

        if self._maybe_sem:
            return self._maybe_sem

        if not status:
            status = await self._status(timeout=timeout)

        self._maybe_sem = asyncio.BoundedSemaphore(status.concurrency)
        return self._maybe_sem

    async def close(self) -> None:
        """Cancel all running queries and close the underlying session."""
        if self._maybe_session and not self._maybe_session.closed:
            # do not care if this fails
            with suppress(CallError):
                _ = await self.cancel_queries()

            # is raised when there are still active queries. that's ok
            with suppress(aiohttp.ServerDisconnectedError):
                await self._maybe_session.close()

    async def _status(
        self,
        timeout: Union[ClientTimeout, object] = sentinel,
    ) -> "Status":
        try:
            async with self._session().get(
                url=urljoin(self._url, "status"), timeout=timeout
            ) as response:
                text = await response.text()
        except aiohttp.ClientError as err:
            raise _to_client_error(err) from err

        slots = 0
        free_slots = None
        cooldown_secs = 0
        concurrency = self._concurrency

        try:
            match_slots_overall = re.findall("Rate limit: (\\d+)", text)
            match_slots_available = re.findall("(\\d+) slots available now", text)
            match_cooldowns = re.findall("Slot available after: .+, in (\\d+) seconds", text)

            (slots,) = match_slots_overall
            slots = int(slots) or None

            if slots:
                cooldowns = [int(secs) for secs in match_cooldowns]

                if match_slots_available:
                    free_slots = int(match_slots_available[0])
                else:
                    free_slots = slots - len(cooldowns)

                cooldown_secs = 0 if free_slots > 0 else min(cooldowns)

                # pick the server's concurrent query limit if > 0 and < self._concurrency,
                # or self._concurrency otherwise
                concurrency = min(slots or self._concurrency, self._concurrency)
        except ValueError as err:
            raise _to_client_error(response) from err

        self._maybe_any_status = Status(
            slots=slots,
            free_slots=free_slots,
            cooldown_secs=cooldown_secs,
            concurrency=concurrency,
        )
        return self._maybe_any_status

    async def status(self) -> Status:
        """
        Check the current API status.

        Raises:
            ClientError: if the status could not be looked up
        """
        return await self._status()

    async def cancel_queries(self) -> int:
        """
        Cancel all running queries.

        This can be used to terminate runaway queries that prevent you from sending new ones.

        Returns:
            the number of terminated queries

        Raises:
            ClientError: if the request to cancel queries failed
        """
        session = self._session()
        endpoint = urljoin(self._url, "kill_my_queries")
        try:
            async with session.get(endpoint) as response:
                body = await response.text()
                killed_pids = re.findall("\\(pid (\\d+)\\)", body)
                return len(set(killed_pids))
        except aiohttp.ClientError as err:
            raise _to_client_error(err) from err

    async def run_query(self, query: Query) -> None:
        """
        Send a query to the API, and await its completion.

        "Running" the query entails acquiring a connection from the pool, waiting for a slot
        to open up, the query requests themselves (which may be retried), status requests
        when the server is busy, and cooldown periods.

        The query runner is invoked before every try.

        To run multiple queries concurrently, wrap the returned coroutines in an ``asyncio`` task,
        f.e. with ``asyncio.create_task()`` and subsequent ``asyncio.gather()``.

        Args:
            query: the query to run on this API instance

        Raises:
            ClientError: when query or status requests fail. If the query was retried, the error
                         of the last try will be raised. The same exception is also captured in
                         ``query.error``.
        """
        if query.done:
            return  # nothing to do

        if query.nb_tries > 0:
            query.reset()  # reset failed queries

        while True:
            await self._invoke_runner(query)
            if query.done:
                return
            await self._run_query_once(query)

    async def _invoke_runner(self, query: Query) -> None:
        try:
            await self._runner(query)
        except ClientError:
            raise
        except BaseException as err:
            raise RunnerError(err) from err

    async def _run_query_once(self, query: Query) -> None:
        logger = query.logger or logging.getLogger(f"{type(self).__module__}.{type(self).__name__}")

        if query.done:
            return

        query_mut = query._mutator()

        query_mut.begin_try()

        acquired_slot = False

        req_timeout = aiohttp.ClientTimeout(
            total=float(query.timeout_secs) + query.request_timeout.total_without_query_secs,
            connect=None,
            sock_connect=query.request_timeout.sock_connect_secs,
            sock_read=query.request_timeout.each_sock_read_secs,
        )

        try:
            await self._wait_for_slot(query)
            acquired_slot = True

            query_mut.begin_request()

            logger.info(f"call api for {query}")

            async with self._session().get(
                url=urljoin(self._url, "interpreter"),
                params={"data": query.code},
                timeout=req_timeout,
            ) as response:
                query_mut.succeed_try(
                    response=await _result_or_raise(response, query.kwargs),
                    response_bytes=response.content.total_bytes,
                )

        except aiohttp.ClientError as err:
            query_mut.fail_try(_to_client_error(err))

        except asyncio.TimeoutError as err:
            if query.run_timeout_elapsed:
                query_err = GiveupError(kwargs=query.kwargs, after_secs=query.run_duration_secs)
            else:
                assert not query.run_timeout_secs or acquired_slot
                query_err = CallTimeoutError(cause=err, after_secs=req_timeout.total)
            query_mut.fail_try(query_err)

        except ClientError as err:
            query_mut.fail_try(err)

        finally:
            query_mut.end_try()
            if acquired_slot:
                self._maybe_sem.release()

    async def _wait_for_slot(self, query: Query) -> None:
        def next_timeout() -> aiohttp.ClientTimeout:
            if query.run_timeout_secs:
                remaining = query.run_timeout_secs - query.run_duration_secs
                if remaining <= 0.0:
                    raise asyncio.TimeoutError()  # no point delaying the inevitable
            else:
                remaining = None  # no limit

            return aiohttp.ClientTimeout(total=remaining)

        logger = query.logger or logging.getLogger(f"{type(self).__module__}.{type(self).__name__}")

        check_cooldown = (
            isinstance(query.error, QueryRejectError)
            and query.error.cause == QueryRejectCause.TOO_MANY_QUERIES
        )

        if check_cooldown:
            # If this client is running too many queries, we can check the status for a
            # cooldown period. This request failing is a bit of an edge case.
            # 'query.error' will be overwritten, which means we will not check for a
            # cooldown in the next iteration.
            status = await self._status(timeout=next_timeout())

            if (timeout := next_timeout()) and status.cooldown_secs > timeout.total:
                raise GiveupError(kwargs=query.kwargs, after_secs=query.run_duration_secs)

            logger.info(f"{query} has cooldown for {status.cooldown_secs:.1f}s")
            await asyncio.sleep(status.cooldown_secs)

        # This requests an API status if we haven't done so already.
        rate_limiter = await self._rate_limiter(timeout=next_timeout())

        # Limit the concurrent query requests to the number of slots available.
        if rate_limiter.locked():
            logger.info(f"{query} has to wait for a slot")

        await asyncio.wait_for(
            fut=rate_limiter.acquire(),
            timeout=next_timeout().total,
        )
