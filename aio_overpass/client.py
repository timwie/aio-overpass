"""Interface for making API calls."""

import asyncio
import logging
import re
import sys
from contextlib import suppress
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urljoin

from aio_overpass import __version__
from aio_overpass.error import (
    CallError,
    ClientError,
    GiveupError,
    RunnerError,
    _result_or_raise,
    _to_client_error,
)
from aio_overpass.query import DefaultQueryRunner, Query, QueryRunner

import aiohttp


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
        self._maybe_sem: Optional[asyncio.BoundedSemaphore] = None

    def _session(self) -> aiohttp.ClientSession:
        """The session used for all requests of this client."""
        if not self._maybe_session or self._maybe_session.closed:
            headers = {"User-Agent": self._user_agent}
            self._maybe_session = aiohttp.ClientSession(headers=headers)

        return self._maybe_session

    async def _rate_limiter(self, **kwargs) -> asyncio.BoundedSemaphore:
        """
        A rate-limiting semaphore for queries.

        This semaphore can be acquired as many times as there are query slots at the API instance.
        If all slots are acquired, further queries need to wait until a slot is released.
        """
        if self._maybe_sem:
            return self._maybe_sem

        session = self._session()
        status = await self._status(session, **kwargs)
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

    async def _status(self, session: aiohttp.ClientSession, **kwargs) -> "Status":
        try:
            async with session.get(url=urljoin(self._url, "status"), **kwargs) as response:
                text = await response.text()
        except aiohttp.ClientError as err:
            raise _to_client_error(err) from err

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

                return Status(
                    slots=slots,
                    free_slots=free_slots,
                    cooldown_secs=cooldown_secs,
                    concurrency=concurrency,
                )

            return Status(
                slots=slots,
                free_slots=None,
                cooldown_secs=0,
                concurrency=self._concurrency,
            )

        except ValueError as err:
            raise _to_client_error(response) from err

    async def status(self) -> Status:
        """
        Check the current API status.

        Raises:
            ClientError: if the status could not be looked up
        """
        session = self._session()
        return await self._status(session)

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

        Args:
            query: the query to run on this API instance

        Raises:
            ClientError: when query or status requests fail. If the query was retried, the error
                         of the last try will be raised. The same exception is also captured in
                         `query.error`.
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

        loop = asyncio.get_event_loop()

        if query._time_start <= 0:
            query._time_start = loop.time()

        query._time_start_try = 0.0
        query._time_end_try = 0.0
        query._nb_tries += 1

        try:
            session = self._session()
            rate_limiter = await self._rate_limiter(timeout=_next_timeout(query))

            if query._has_cooldown():
                # If this client is running too many queries, we can check the status for a
                # cooldown period. This request failing is a bit of an edge case.
                # 'query.error' will be overwritten, which means we will not check for a
                # cooldown in the next iteration.
                status = await self._status(session=session, timeout=_next_timeout(query))

                if (timeout := _next_timeout_secs(query)) and status.cooldown_secs > timeout:
                    raise _giveup_error(query, loop)

                logger.info(f"{query} has cooldown for {status.cooldown_secs:.1f}s")
                await asyncio.sleep(status.cooldown_secs)

            # Limit the concurrent query requests to the number of slots available.
            if rate_limiter.locked():
                logger.info(f"{query} has to wait for a slot")

            await asyncio.wait_for(
                fut=rate_limiter.acquire(),
                timeout=_next_timeout(query).total,
            )

            try:
                query._time_start_try = loop.time()

                logger.info(f"call api for {query}")

                async with session.get(
                    url=urljoin(self._url, "interpreter"),
                    params={"data": query.code},
                    timeout=_next_timeout(query),
                ) as response:
                    query._time_end_try = loop.time()
                    query._result_set = await _result_or_raise(response, query.kwargs)
                    query._result_set_bytes = response.content.total_bytes
                    query._error = None
            finally:
                rate_limiter.release()

        except aiohttp.ClientError as err:
            query._error = _to_client_error(err)

        except asyncio.TimeoutError:
            query._error = _giveup_error(query, loop)

        except ClientError as err:
            query._error = err


def _next_timeout_secs(query: Query) -> Optional[float]:
    if query.run_timeout_secs:
        # use epsilon since 0 means "no timeout"
        return max(sys.float_info.epsilon, query.run_timeout_secs - query.run_duration_secs)
    return None


def _next_timeout(query: Query) -> aiohttp.ClientTimeout:
    return aiohttp.ClientTimeout(total=_next_timeout_secs(query))


def _giveup_error(query: Query, loop: asyncio.AbstractEventLoop) -> GiveupError:
    return GiveupError(kwargs=query.kwargs, after_secs=loop.time() - query._time_start)
