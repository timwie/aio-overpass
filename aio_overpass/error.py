"""
Error types.

```
                            (ClientError)
                                  ╷
    ┌──────────────┬──────────────┼────────────┬────────────────┐
    ╵              ╵              ╵            ╵                ╵
CallError     RunnerError   (QueryError)   GiveupError    ResponseError
                                  ╷                             ╷
         ┌────────────────────────┼──────────────────────┐      │
         ╵                        ╵                      ╵      ╵
QueryLanguageError         QueryRejectError          QueryResponseError
```
"""

import html
import re
from dataclasses import dataclass
from enum import Enum, auto
from json import JSONDecodeError
from typing import Optional, Union, no_type_check

import aiohttp
import aiohttp.typedefs


__docformat__ = "google"
__all__ = (
    "ClientError",
    "CallError",
    "ResponseError",
    "GiveupError",
    "QueryError",
    "QueryLanguageError",
    "QueryRejectError",
    "QueryRejectCause",
    "QueryResponseError",
    "RunnerError",
)


class ClientError(Exception):
    """Base exception for failed Overpass API requests and queries."""


@dataclass
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

    def __post_init__(self) -> None:
        # imitate "raise QueryRunnerError(...) from cause"
        self.__cause__ = self.cause

    def __str__(self) -> str:
        return str(self.cause)


@dataclass
class CallError(ClientError):
    """
    Failed to make an API request.

    This error is raised when the client failed to get any response,
    f.e. due to connection issues.

    Attributes:
        cause: the exception that caused this error
    """

    cause: aiohttp.ClientError

    def __post_init__(self) -> None:
        # imitate "raise CallError(...) from cause"
        self.__cause__ = self.cause

    def __str__(self) -> str:
        return str(self.cause)


@dataclass
class ResponseError(ClientError):
    """
    Unexpected API response.

    This error is raised when a request fails, but we can't specifically say why.
    This may indicate a bug on our end, since the client is meant to process almost any
    response of an Overpass API instance.

    Attributes:
        request_info: Contains information about request.
        history: History from failed response.
        status: HTTP status code of response, e.g. ``400``.
        message: Message of response, e.g. ``"OK"``.
        headers: Headers in response, a list of pairs.
    """

    request_info: aiohttp.RequestInfo
    history: tuple[aiohttp.ClientResponse, ...]
    status: int
    message: str
    headers: Optional[aiohttp.typedefs.LooseHeaders]

    @property
    def response(self) -> aiohttp.ClientResponse:
        """Client response returned by ``aiohttp.ClientSession.request()`` and family."""
        return self.history[-1]

    def __str__(self) -> str:
        return (
            f"unexpected response: {self.status}, {self.message!r}, {self.request_info.real_url!r}"
        )


@dataclass
class GiveupError(ClientError):
    """
    The client spent too long running a query, and gave up.

    This error is raised when the run timeout duration set by a query runner is exceeded.

    Attributes:
        kwargs: the query's ``kwargs``
        after_secs: the total time spent on the query
    """

    kwargs: dict
    after_secs: float

    def __str__(self) -> str:
        query = f"query {self.kwargs}" if self.kwargs else "query <no kwargs>"
        return f"gave up on {query} after {self.after_secs:.01f} seconds"


@dataclass
class QueryError(ClientError):
    """
    Base exception for queries that failed at the Overpass API server.

    Attributes:
        kwargs: the query's ``kwargs``
        remarks: the error remarks provided by the API
    """

    kwargs: dict
    remarks: list[str]

    def __str__(self) -> str:
        query = f"query {self.kwargs}" if self.kwargs else "query <no kwargs>"
        first = f"'{self.remarks[0]}'"
        rest = f" (+{len(self.remarks) - 1} more)" if len(self.remarks) > 1 else ""
        return f"{query} failed: {first}{rest}"


@dataclass
class QueryResponseError(ResponseError, QueryError):
    """
    Unexpected query response.

    This error is raised when a query fails (thus extends ``QueryError``),
    but we can't specifically say why (thus also extends ``ResponseError``).
    """

    def __str__(self) -> str:
        return QueryError.__str__(self)


@dataclass
class QueryLanguageError(QueryError):
    """
    Indicates the query's QL code is not valid.

    Retrying is pointless when encountering this error.
    """


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
        if self == QueryRejectCause.TOO_BUSY:
            return "server too busy"
        if self == QueryRejectCause.TOO_MANY_QUERIES:
            return "too many queries"
        if self == QueryRejectCause.EXCEEDED_TIMEOUT:
            return "exceeded 'timeout'"
        if self == QueryRejectCause.EXCEEDED_MAXSIZE:
            return "exceeded 'maxsize'"
        raise AssertionError()


@dataclass
class QueryRejectError(QueryError):
    """
    A query was rejected or cancelled by the API server.

    Attributes:
        cause: why the query was rejected or cancelled
    """

    cause: QueryRejectCause

    def __str__(self) -> str:
        if self.cause in (QueryRejectCause.TOO_BUSY, QueryRejectCause.TOO_MANY_QUERIES):
            rejection = "query rejected"
        else:
            rejection = "query cancelled"

        return f"{rejection}: {self.cause}"


@no_type_check
def _to_client_error(
    obj: Union[aiohttp.ClientResponse, aiohttp.ClientError]
) -> Union[CallError, ResponseError]:
    """
    Build a ``ClientError`` from either an ``aiohttp`` client error or an unrecognized response.

    Returns:
        - ``CallError`` if ``obj`` is an ``aiohttp.ClientError``,
          but not an ``aiohttp.ClientResponseError``.
        - ``ResponseError`` if ``obj`` is a response or an ``aiohttp.ClientResponseError``.
    """
    if not isinstance(obj, (aiohttp.ClientResponseError, aiohttp.ClientResponse)):
        return CallError(cause=obj)

    error = ResponseError(
        request_info=obj.request_info,
        history=obj.history,
        status=obj.status,
        message=obj.message if isinstance(obj, aiohttp.ClientResponseError) else obj.reason,
        headers=obj.headers,
    )

    if isinstance(obj, aiohttp.ClientResponseError):
        error.__cause__ = obj

    return error


async def _result_or_raise(response: aiohttp.ClientResponse, query_kwargs: dict) -> dict:
    """
    Try to extract the query result set from a response.

    Raises:
        CallError: When there is any sort of connection error.
        ResponseError: When encountering an unexpected response.
        RejectError: When encountering "Too Many Requests" or "Gateway Timeout";
                     when there's a JSON remark indicating query rejection or cancellation;
                     when there's an HTML error message indicating query rejection or cancellation.
        QueryError: When there's any other JSON remark or HTML error message.
    """
    await _raise_for_html_response(response, query_kwargs)

    try:
        json = await response.json()
    except aiohttp.ClientResponseError as err:
        raise _to_client_error(err) from err
    except JSONDecodeError as err:
        raise _response_error(response) from err

    if json is None:
        raise _response_error(response)

    _raise_for_json_remarks(response, json, query_kwargs)

    _raise_for_status(response, query_kwargs)

    return json


def _raise_for_status(response: aiohttp.ClientResponse, query_kwargs: dict) -> None:
    """
    Raise a fitting exception based on the status code.

    Raises:
        RejectError: for status "Too Many Requests" and "Gateway Timeout"
        ResponseError: for any status >= 400

    References:
        - HTTP status codes: http://overpass-api.de/command_line.html
    """
    if response.status == _TOO_MANY_REQUESTS:
        raise QueryRejectError(
            kwargs=query_kwargs, remarks=[], cause=QueryRejectCause.TOO_MANY_QUERIES
        )

    if response.status == _GATEWAY_TIMEOUT:
        raise QueryRejectError(kwargs=query_kwargs, remarks=[], cause=QueryRejectCause.TOO_BUSY)

    if response.status >= _BAD_REQUEST:
        raise _to_client_error(response)


_BAD_REQUEST = 400
_TOO_MANY_REQUESTS = 429
_GATEWAY_TIMEOUT = 504


def _raise_for_json_remarks(
    response: aiohttp.ClientResponse, json: dict, query_kwargs: dict
) -> None:
    """
    Raise a fitting exception based on a remark in a JSON response.

    Raises:
        RejectError: if the API server remarked that the query was rejected or cancelled
        QueryError: if the API server remarked something else
    """
    remark = json.get("remark")
    if not remark:
        return

    timeout_cause = _match_reject_cause(remark)
    if timeout_cause:
        raise QueryRejectError(kwargs=query_kwargs, remarks=[remark], cause=timeout_cause)

    raise _query_response_error(kwargs=query_kwargs, remarks=[remark], response=response)


async def _raise_for_html_response(response: aiohttp.ClientResponse, query_kwargs: dict) -> None:
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
        raise _to_client_error(response)

    if any(_is_ql_error(msg) for msg in errors):
        raise QueryLanguageError(kwargs=query_kwargs, remarks=errors)

    reject_causes = [cause for err in errors if (cause := _match_reject_cause(err))]

    if reject_causes:
        raise QueryRejectError(kwargs=query_kwargs, remarks=errors, cause=reject_causes[0])

    raise _query_response_error(kwargs=query_kwargs, remarks=errors, response=response)


def _match_reject_cause(error_msg: str) -> Optional[QueryRejectCause]:
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
        return QueryRejectCause.TOO_MANY_QUERIES

    if "The server is probably too busy to handle your request" in error_msg:
        return QueryRejectCause.TOO_BUSY

    if "Query timed out" in error_msg:
        return QueryRejectCause.EXCEEDED_TIMEOUT

    if "out of memory" in error_msg:
        return QueryRejectCause.EXCEEDED_MAXSIZE

    return None


def _is_ql_error(message: str) -> bool:
    return "encoding error:" in message or "parse error:" in message or "static error:" in message


def _response_error(response: aiohttp.ClientResponse) -> ResponseError:
    return ResponseError(
        request_info=response.request_info,
        history=response.history,
        status=response.status,
        message=str(response.reason) if response.reason else "",
        headers=response.headers,
    )


def _query_response_error(
    kwargs: dict,
    remarks: list[str],
    response: aiohttp.ClientResponse,
) -> QueryResponseError:
    return QueryResponseError(
        kwargs=kwargs,
        remarks=remarks,
        request_info=response.request_info,
        history=response.history,
        status=response.status,
        message=str(response.reason) if response.reason else "",
        headers=response.headers,
    )
