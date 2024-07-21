"""
Error types.

```
                            (ClientError)
                                  ╷
                   ┌──────────────┼────────────┬────────────────┬────────────────┐
                   ╵              ╵            ╵                ╵                ╵
               RunnerError   (QueryError)   GiveupError    ResponseError     CallError
                                  ╷                             ╷                ╷
         ┌────────────────────────┼──────────────────────┐      │                │
         ╵                        ╵                      ╵      ╵                ╵
QueryLanguageError         QueryRejectError          QueryResponseError   CallTimeoutError
```
"""

import asyncio
import html
import logging
import math
import re
from dataclasses import dataclass
from enum import Enum, auto
from json import JSONDecodeError
from typing import NoReturn, TypeAlias, TypeGuard

import aiohttp
import aiohttp.typedefs


__docformat__ = "google"
__all__ = (
    "ClientError",
    "CallError",
    "CallTimeoutError",
    "ResponseError",
    "ResponseErrorCause",
    "GiveupError",
    "GiveupCause",
    "QueryError",
    "QueryLanguageError",
    "QueryRejectError",
    "QueryRejectCause",
    "QueryResponseError",
    "RunnerError",
    "is_call_err",
    "is_call_timeout",
    "is_exceeding_maxsize",
    "is_exceeding_timeout",
    "is_gateway_rejection",
    "is_giveup_err",
    "is_rejection",
    "is_runtime_rejection",
    "is_server_error",
    "is_too_busy",
    "is_too_many_queries",
)


class ClientError(Exception):
    """Base exception for failed Overpass API requests and queries."""

    @property
    def should_retry(self) -> bool:
        """Returns ``True`` if it's worth retrying when encountering this error."""
        return False


@dataclass(kw_only=True)
class RunnerError(ClientError):
    """
    The query runner raised an exception.

    This is an unexpected error, in contrast to the runner intentionally
    raising ``query.error`` to stop retrying. The cause of this error
    is therefore anything but a ``ClientError``.

    Attributes:
        cause: the exception that caused this error
    """

    cause: BaseException

    @property
    def should_retry(self) -> bool:
        """Returns ``True`` if it's worth retrying when encountering this error."""
        return False

    def __str__(self) -> str:
        return str(self.cause)


@dataclass(kw_only=True)
class CallError(ClientError):
    """
    Failed to make an API request.

    This error is raised when the client failed to get any response,
    f.e. due to connection issues.

    Attributes:
        cause: the exception that caused this error
    """

    cause: aiohttp.ClientError

    @property
    def should_retry(self) -> bool:
        """Returns ``True`` if it's worth retrying when encountering this error."""
        return True

    def __str__(self) -> str:
        return str(self.cause)


@dataclass(kw_only=True)
class CallTimeoutError(CallError):
    """
    An API request timed out.

    Attributes:
        cause: the exception that caused this error
        after_secs: the configured timeout for the request
    """

    cause: asyncio.TimeoutError  # type: ignore[assignment]
    after_secs: float

    @property
    def should_retry(self) -> bool:
        """Returns ``True`` if it's worth retrying when encountering this error."""
        return True

    def __str__(self) -> str:
        return str(self.cause)


ResponseErrorCause: TypeAlias = aiohttp.ClientResponseError | JSONDecodeError | ValueError
"""Causes for a ``ResponseError``."""


@dataclass(kw_only=True)
class ResponseError(ClientError):
    """
    Unexpected API response.

    On the one hand, this can be an error that happened on the Overpass API instance,
    which is usually signalled by a status code ``>= 500``. In rare cases,
    the ``cause`` being a ``JSONDecodeError`` also signals this, since it can happen
    that the API returns a cutoff JSON response. In both of these cases,
    ``is_server_error()`` will return ``True``.

    On the other hand, this error may indicate that a request failed, but we can't
    specifically say why. This could be a bug on our end, since the client
    is meant to process almost any response of an Overpass API instance.
    Here, ``is_server_error()`` will return ``False``, and the default query runner
    will log the response body.

    Attributes:
        response: the unexpected response
        body: the response body
        cause: an optional exception that may have caused this error
    """

    response: aiohttp.ClientResponse
    body: str
    cause: ResponseErrorCause | None

    @property
    def should_retry(self) -> bool:
        """Returns ``True`` if it's worth retrying when encountering this error."""
        return True

    @property
    def is_server_error(self) -> bool:
        """Returns ``True`` if this presumably a server-side error."""
        # see class doc for details
        return self.response.status >= 500 or isinstance(self.cause, JSONDecodeError)

    def __str__(self) -> str:
        if self.cause is None:
            return f"unexpected response ({self.response.status})"
        return f"unexpected response ({self.response.status}): {self.cause}"


class GiveupCause(Enum):
    """Details on why a query was given up on."""

    RUN_TIMEOUT_BEFORE_STATUS_CALL = auto()
    """Query's ``run_timeout_secs`` elapsed before a status call before the actual query call."""

    RUN_TIMEOUT_BY_COOLDOWN = auto()
    """Query received a timeout that would exceed its remaining ``run_timeout_secs``."""

    RUN_TIMEOUT_BEFORE_QUERY_CALL = auto()
    """Query's ``run_timeout_secs`` elapsed before the query call."""

    EXPECTING_QUERY_TIMEOUT = auto()
    """
    The query's limited [timeout:*] setting is likely too low.

    A query's [timeout:*] setting might be lowered by the client to the remainder of
    ``run_timeout_secs``. If that happens, and that duration is also lower than a duration
    after which it was cancelled at the server previously, then this is the cause to give
    up on the query.

    See Also:
        ``QueryRejectError.timed_out_after_secs``
    """

    RUN_TIMEOUT_DURING_QUERY_CALL = auto()
    """Query's ``run_timeout_secs`` elapsed while making the query call, before any response."""


@dataclass(kw_only=True)
class GiveupError(ClientError):
    """
    The client spent or would spend too long running a query, and gave up.

    This error is raised when the run timeout duration set by a query runner
    is or would be exceeded.

    Attributes:
        kwargs: the query's ``kwargs``
        after_secs: the total time spent on the query
        cause: why the query was given up on
    """

    kwargs: dict
    after_secs: float
    cause: GiveupCause

    @property
    def should_retry(self) -> bool:
        """Returns ``True`` if it's worth retrying when encountering this error."""
        return False

    def __str__(self) -> str:
        return f"gave up on query{self.kwargs!r} after {self.after_secs:.01f} seconds"


@dataclass(kw_only=True)
class QueryError(ClientError):
    """
    Base exception for queries that failed at the Overpass API server.

    Attributes:
        kwargs: the query's ``kwargs``
        remarks: the error remarks provided by the API
    """

    kwargs: dict
    remarks: list[str]

    @property
    def should_retry(self) -> bool:
        """Returns ``True`` if it's worth retrying when encountering this error."""
        return False

    def __str__(self) -> str:
        first = f"'{self.remarks[0]}'"
        rest = f" (+{len(self.remarks) - 1} more)" if len(self.remarks) > 1 else ""
        return f"query{self.kwargs!r} failed: {first}{rest}"


@dataclass(kw_only=True)
class QueryResponseError(ResponseError, QueryError):
    """
    Unexpected query response.

    This error is raised when a query fails (thus extends ``QueryError``),
    but we can't specifically say why (thus also extends ``ResponseError``).
    """

    @property
    def should_retry(self) -> bool:
        """Returns ``True`` if it's worth retrying when encountering this error."""
        return ResponseError.should_retry.fget(self)  # type: ignore[attr-defined]

    def __str__(self) -> str:
        if self.remarks:
            first = f"'{self.remarks[0]}'"
            rest = f" (+{len(self.remarks) - 1} more)" if len(self.remarks) > 1 else ""
            return f"query{self.kwargs!r} failed: {first}{rest}"

        return f"query{self.kwargs!r} failed with status {self.response.status}"


@dataclass(kw_only=True)
class QueryLanguageError(QueryError):
    """
    Indicates the query's QL code is not valid.

    Retrying is pointless when encountering this error.
    """

    @property
    def should_retry(self) -> bool:
        """Returns ``True`` if it's worth retrying when encountering this error."""
        return False


class QueryRejectCause(Enum):
    """Details why a query was rejected or cancelled by an API server."""

    TOO_BUSY = auto()
    """
    Gateway rejection. The server has already so much load that the request cannot be executed.

    Smaller ``[timeout:*]`` and/or ``[maxsize:*]`` values might make the request acceptable.
    """

    TOO_MANY_QUERIES = auto()
    """
    Gateway rejection. There are no open slots for queries from your IP address.

    Running queries take up a slot, and the number of slots is limited. A client
    will only run as many concurrent requests as there are slots, which should make this
    a rare error, assuming you are not making requests through another client.
    """

    EXCEEDED_TIMEOUT = auto()
    """
    Runtime rejection. The query has been (or surely will be) running longer than its proposed
    ``[timeout:*]``, and has been cancelled by the server.

    A higher ``[timeout:*]`` value might allow the query run to completion, but also makes it
    more likely to be rejected by a server under heavy load, before executing it (see ``TOO_BUSY``).
    """

    EXCEEDED_MAXSIZE = auto()
    """
    Runtime rejection. The memory required to execute the query has (or surely will) exceed
    its proposed ``[maxsize:*]``, and has been cancelled by the server.

    A higher ``[maxsize:*]`` value might allow the query run to completion, but also makes it
    more likely to be rejected by a server under heavy load, before executing it (see ``TOO_BUSY``).
    """

    def __str__(self) -> str:
        match self:
            case QueryRejectCause.TOO_BUSY:
                return "server too busy"
            case QueryRejectCause.TOO_MANY_QUERIES:
                return "too many queries"
            case QueryRejectCause.EXCEEDED_TIMEOUT:
                return "exceeded 'timeout'"
            case QueryRejectCause.EXCEEDED_MAXSIZE:
                return "exceeded 'maxsize'"
            case _:
                raise AssertionError


@dataclass(kw_only=True)
class QueryRejectError(QueryError):
    """
    A query was rejected or cancelled by the API server.

    Attributes:
        cause: why the query was rejected or cancelled
        timed_out_after_secs: if ``cause`` is ``EXCEEDED_TIMEOUT``, this is the amount
                              of seconds after which the query timed out
        oom_using_mib: if ```cause`` is ``EXCEEDED_MAXSIZE``, this is the amount of RAM
                       the query used before it ran out
    """

    cause: QueryRejectCause
    timed_out_after_secs: int | None
    oom_using_mib: int | None

    @property
    def should_retry(self) -> bool:
        """Returns ``True`` if it's worth retrying when encountering this error."""
        return True

    def __str__(self) -> str:
        match self.cause:
            case QueryRejectCause.TOO_BUSY | QueryRejectCause.TOO_MANY_QUERIES:
                rejection = "query rejected"
            case QueryRejectCause.EXCEEDED_TIMEOUT:
                rejection = f"query cancelled after {self.timed_out_after_secs}s"
            case QueryRejectCause.EXCEEDED_MAXSIZE:
                rejection = f"query cancelled using {self.oom_using_mib}"
            case _:
                raise AssertionError(self.cause)

        return f"{rejection}: {self.cause}"


async def _raise_for_request_error(err: aiohttp.ClientError) -> NoReturn:
    """
    Raise an exception caused by the given request error.

    Raises:
        - ``CallError`` if ``obj`` is an ``aiohttp.ClientError``,
          but not an ``aiohttp.ClientResponseError``.
        - ``ResponseError`` otherwise.
    """
    if isinstance(err, aiohttp.ClientResponseError):
        response = err.history[-1]
        await _raise_for_response(response, err)

    raise CallError(cause=err) from err


async def _raise_for_response(
    response: aiohttp.ClientResponse,
    cause: ResponseErrorCause | None,
) -> NoReturn:
    """Raise a ``ResponseError`` with an optional cause."""
    err = ResponseError(
        response=response,
        body=await response.text(),
        cause=cause,
    )
    if cause:
        raise err from cause
    raise err


async def _result_or_raise(
    response: aiohttp.ClientResponse,
    query_kwargs: dict,
    query_logger: logging.Logger,
) -> dict:
    """
    Try to extract the query result set from a response.

    Raises:
        CallError: When there is any sort of connection error.
        RejectError: When encountering "Too Many Requests" or "Gateway Timeout";
                     when there's a JSON remark indicating query rejection or cancellation;
                     when there's an HTML error message indicating query rejection or cancellation.
        QueryError: When there's any other JSON remark or HTML error message.
        ResponseError: When encountering an unexpected response.
    """
    await __raise_for_plaintext_result(response)

    await __raise_for_html_result(response, query_kwargs, query_logger)

    return await __raise_for_json_result(response, query_kwargs, query_logger)


async def __raise_for_json_result(
    response: aiohttp.ClientResponse,
    query_kwargs: dict,
    query_logger: logging.Logger,
) -> dict:
    try:
        json = await response.json()
        if json is None:
            await _raise_for_response(response, cause=None)
    except aiohttp.ClientResponseError as err:
        await _raise_for_response(response, cause=err)
    except JSONDecodeError as err:
        await _raise_for_response(response, cause=err)

    if remark := json.get("remark"):
        if timeout_cause := __match_reject_cause(remark, query_logger):
            raise QueryRejectError(
                kwargs=query_kwargs,
                remarks=[remark],
                cause=timeout_cause,
                oom_using_mib=__match_oom_after(remark),
                timed_out_after_secs=__match_timeout_after(remark),
            )

        raise QueryResponseError(
            response=response,
            body=await response.text(),
            cause=None,
            kwargs=query_kwargs,
            remarks=[remark],
        )

    expected_fields = ("version", "generator", "osm3s", "elements")
    expected_osm3s_fields = ("timestamp_osm_base", "copyright")
    if any(f not in json for f in expected_fields) or any(
        f not in json["osm3s"] for f in expected_osm3s_fields
    ):
        await _raise_for_response(response, cause=None)

    return json


async def __raise_for_html_result(
    response: aiohttp.ClientResponse,
    query_kwargs: dict,
    query_logger: logging.Logger,
) -> None:
    """
    Raise a fitting exception based on error remarks in an HTML response.

    Raises:
        RejectError: if one of the error remarks indicate that the query was rejected or cancelled
        QueryError: when encountering other error remarks
        ResponseError: when error remarks cannot be extracted from the response
    """
    if response.content_type != "text/html":
        return

    text = await response.text()

    pattern = re.compile("Error</strong>: (.+?)</p>", re.DOTALL)
    errors = [html.unescape(err.strip()) for err in pattern.findall(text)]

    if not errors:  # unexpected format
        await _raise_for_response(response, cause=None)

    if any(__is_ql_error(msg, query_logger) for msg in errors):
        raise QueryLanguageError(kwargs=query_kwargs, remarks=errors)

    reject_causes = [cause for err in errors if (cause := __match_reject_cause(err, query_logger))]
    oom_using_mib = next((mib for err in errors if (mib := __match_oom_after(err))), None)
    timed_out_after_secs = next(
        (secs for err in errors if (secs := __match_timeout_after(err))), None
    )

    if reject_causes:
        raise QueryRejectError(
            kwargs=query_kwargs,
            remarks=errors,
            cause=reject_causes[0],
            oom_using_mib=oom_using_mib,
            timed_out_after_secs=timed_out_after_secs,
        )

    raise QueryResponseError(
        response=response,
        body=await response.text(),
        cause=None,
        kwargs=query_kwargs,
        remarks=errors,
    )


async def __raise_for_plaintext_result(response: aiohttp.ClientResponse) -> None:
    if response.content_type != "text/plain":
        return
    await _raise_for_response(response, cause=None)


def __match_reject_cause(error_msg: str, query_logger: logging.Logger) -> QueryRejectCause | None:
    """
    Check if the given error message indicates that a query was rejected or cancelled.

    AFAIK, neither the 'remarks' in JSON responses, nor the errors listed in HTML responses
    are neatly listed somewhere, but it seems matching a small subset of remarks is enough
    to identify recoverable errors.

    References:
        - Related: https://github.com/DinoTools/python-overpy/issues/62
        - Examples in the API source: https://github.com/drolbr/Overpass-API/search?q=runtime_error
    """
    if "Please check /api/status for the quota of your IP address" in error_msg:
        cause = QueryRejectCause.TOO_MANY_QUERIES

    elif "The server is probably too busy to handle your request" in error_msg:
        cause = QueryRejectCause.TOO_BUSY

    elif "Query timed out" in error_msg:
        cause = QueryRejectCause.EXCEEDED_TIMEOUT

    elif "out of memory" in error_msg:
        cause = QueryRejectCause.EXCEEDED_MAXSIZE

    else:
        cause_cls = QueryRejectCause.__class__.__name__
        query_logger.debug(f"does not match any {cause_cls}: {error_msg!r}")
        return None

    query_logger.debug(f"matches {cause}: {error_msg!r}")
    return cause


def __match_oom_after(error_msg: str) -> int | None:
    pattern = re.compile(
        r"^runtime error: Query run out of memory in \".+\""
        r" at line \d+ using about (\d+) MB of RAM\.$"
    )
    if m := pattern.match(error_msg):
        mb = int(m.group(1))
        return math.ceil((mb * 1000**2) / 1024**2)
    return None


def __match_timeout_after(error_msg: str) -> int | None:
    pattern = re.compile(
        r"^runtime error: Query timed out in \".+\" at line \d+ after (\d+) seconds\.$"
    )
    if m := pattern.match(error_msg):
        return int(m.group(1))
    return None


def __is_ql_error(error_msg: str, query_logger: logging.Logger) -> bool:
    """Check if the given error message indicates that a query has bad QL code."""
    is_ql_error = (
        "encoding error:" in error_msg
        or "parse error:" in error_msg
        or "static error:" in error_msg
    )

    if is_ql_error:
        query_logger.debug(f"is a QL error: {error_msg!r}")
        return True

    query_logger.debug(f"not a QL error: {error_msg!r}")
    return False


def is_call_err(err: ClientError | None) -> TypeGuard[CallError]:
    """``True`` if this is a ``CallError``."""
    return isinstance(err, CallError)


def is_call_timeout(err: ClientError | None) -> TypeGuard[CallTimeoutError]:
    """``True`` if this is a ``CallTimeoutError``."""
    return isinstance(err, CallTimeoutError)


def is_giveup_err(err: ClientError | None) -> TypeGuard[GiveupError]:
    """``True`` if this is a ``GiveupError``."""
    return isinstance(err, GiveupError)


def is_server_error(err: ClientError | None) -> TypeGuard[ResponseError]:
    """``True`` if this is a ``ResponseError`` presumably cause by a server-side error."""
    return isinstance(err, ResponseError) and err.is_server_error


def is_rejection(err: ClientError | None) -> TypeGuard[QueryRejectError]:
    """``True`` if this is a ``QueryRejectError``."""
    return isinstance(err, QueryRejectError)


def is_gateway_rejection(err: ClientError | None) -> TypeGuard[QueryRejectError]:
    """``True`` if this is a ``QueryRejectError`` with gateway rejection."""
    return isinstance(err, QueryRejectError) and err.cause in {
        QueryRejectCause.TOO_MANY_QUERIES,
        QueryRejectCause.TOO_BUSY,
    }


def is_too_many_queries(err: ClientError | None) -> TypeGuard[QueryRejectError]:
    """``True`` if this is a ``QueryRejectError`` with cause ``TOO_MANY_QUERIES``."""
    return isinstance(err, QueryRejectError) and err.cause is QueryRejectCause.TOO_MANY_QUERIES


def is_too_busy(err: ClientError | None) -> TypeGuard[QueryRejectError]:
    """``True`` if this is a ``QueryRejectError`` with cause ``TOO_BUSY``."""
    return isinstance(err, QueryRejectError) and err.cause is QueryRejectCause.TOO_BUSY


def is_runtime_rejection(err: ClientError | None) -> TypeGuard[QueryRejectError]:
    """``True`` if this is a ``QueryRejectError`` with runtime rejection."""
    return isinstance(err, QueryRejectError) and err.cause in {
        QueryRejectCause.EXCEEDED_MAXSIZE,
        QueryRejectCause.EXCEEDED_TIMEOUT,
    }


def is_exceeding_maxsize(err: ClientError | None) -> TypeGuard[QueryRejectError]:
    """``True`` if this is a ``GiveupError`` with cause ``EXCEEDED_MAXSIZE``."""
    return isinstance(err, QueryRejectError) and err.cause is QueryRejectCause.EXCEEDED_MAXSIZE


def is_exceeding_timeout(err: ClientError | None) -> TypeGuard[QueryRejectError]:
    """``True`` if this is a ``GiveupError`` with cause ``EXCEEDED_TIMEOUT``."""
    return isinstance(err, QueryRejectError) and err.cause is QueryRejectCause.EXCEEDED_TIMEOUT
