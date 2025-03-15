import re

from aio_overpass import Client, Query
from aio_overpass.query import RequestTimeout

import pytest


@pytest.mark.asyncio
@pytest.mark.xdist_group(name="fast")
@pytest.mark.parametrize(
    "bad_value",
    [
        -1.0,
        0.0,
        float("inf"),
        float("nan"),
    ],
)
async def test_client_value_errors(bad_value: float):
    with pytest.raises(ValueError, match="'status_timeout_secs' must be finite > 0"):
        _ = Client(status_timeout_secs=bad_value)

    c = Client()

    with pytest.raises(ValueError, match="'timeout_secs' must be finite > 0"):
        await c.cancel_queries(timeout_secs=bad_value)


@pytest.mark.xdist_group(name="fast")
@pytest.mark.parametrize(
    "bad_value",
    [
        -1.0,
        0.0,
        float("inf"),
        float("nan"),
    ],
)
def test_query_float_value_errors(bad_value: float):
    q = Query("some code")

    with pytest.raises(ValueError, match="'maxsize_mib' must be finite > 0"):
        q.maxsize_mib = bad_value

    with pytest.raises(ValueError, match="'run_timeout_secs' must be finite > 0"):
        q.run_timeout_secs = bad_value


@pytest.mark.xdist_group(name="fast")
def test_query_settings_value_errors():
    with pytest.raises(
        ValueError,
        match=re.escape("the '[out:*]' setting is implicitly set to 'json' and should be omitted"),
    ):
        _ = Query(
            """
            [out:xml];
            some code
            """
        )

    with pytest.raises(
        ValueError, match=re.escape("the '[timeout:*]' setting must be an integer > 0")
    ):
        _ = Query(
            """
            [timeout:not a number];
            some code
            """
        )

    with pytest.raises(
        ValueError, match=re.escape("the '[timeout:*]' setting must be an integer > 0")
    ):
        _ = Query(
            """
            [timeout:0];
            some code
            """
        )

    with pytest.raises(
        ValueError, match=re.escape("the '[maxsize:*]' setting must be an integer > 0")
    ):
        _ = Query(
            """
            [maxsize:-1];
            some code
            """
        )

    with pytest.raises(
        ValueError, match=re.escape("the '[maxsize:*]' setting must be an integer > 0")
    ):
        _ = Query(
            """
            [maxsize:0];
            some code
            """
        )

    _ok = Query(
        """
        [timeout:1];
        [maxsize:1];
        some code
        """
    )


@pytest.mark.xdist_group(name="fast")
@pytest.mark.parametrize(
    "bad_value",
    [
        -1.0,
        0.0,
        float("inf"),
        float("nan"),
    ],
)
def test_request_timeout_value_errors(bad_value: float):
    with pytest.raises(ValueError, match="'total_without_query_secs' must be finite > 0"):
        RequestTimeout(total_without_query_secs=bad_value)

    with pytest.raises(ValueError, match="'sock_connect_secs' must be finite > 0"):
        RequestTimeout(sock_connect_secs=bad_value)

    with pytest.raises(ValueError, match="'each_sock_read_secs' must be finite > 0"):
        RequestTimeout(each_sock_read_secs=bad_value)
