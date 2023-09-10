import re

from aio_overpass import Query
from aio_overpass.query import DefaultQueryRunner, QueryRunner

import pytest
from aioresponses import aioresponses


URL_INTERPRETER = re.compile(r"^https://overpass-api\.de/api/interpreter\?data=.+$")
URL_STATUS = "https://overpass-api.de/api/status"
URL_KILL = "https://overpass-api.de/api/kill_my_queries"


@pytest.fixture
def mock_response():
    with aioresponses() as m:
        mock_status = """
        Connected as: 1807920285
        Current time: 2020-11-22T13:32:57Z
        Rate limit: 2
        2 slots available now.
        Currently running queries (pid, space limit, time limit, start time):
        """

        m.get(
            url=URL_STATUS,
            body=mock_status,
            status=200,
        )

        m.get(
            url=URL_KILL,
            body="",
            status=200,
        )

        yield m


class VerifyingQueryRunner(QueryRunner):
    """
    Same as the default runner, but with calls to ``verify_query_state()``
    before and after yielding to it.
    """

    def __init__(self, *args, **kwargs) -> None:
        self._default = DefaultQueryRunner(*args, **kwargs)
        self._prev_nb_tries = None

    async def __call__(self, query: Query) -> None:
        self._verify_nb_tries(query)
        verify_query_state(query)
        await self._default(query)
        verify_query_state(query)

    def _verify_nb_tries(self, query: Query) -> None:
        if self._prev_nb_tries is None:
            msg = "expected zero tries yet"
            assert query.nb_tries == 0, msg
        elif query.nb_tries == 0:
            # was reset
            pass
        else:
            msg = f"expected try #{self._prev_nb_tries + 1} but got {query.nb_tries}"
            assert query.nb_tries == self._prev_nb_tries + 1, msg

        self._prev_nb_tries = query.nb_tries


def verify_query_state(query: Query) -> None:
    """Assert query state consistency."""
    assert query.nb_tries >= 0
    assert query.maxsize_mib >= 0
    assert query.timeout_secs >= 1
    assert query.run_timeout_secs is None or query.run_timeout_secs > 0.0
    assert query.code.count("[timeout:") == 1
    assert query.code.count("[maxsize:") == 1
    assert len(query.cache_key) == 64
    assert query.copyright

    assert str(query)  # just test this doesn't raise
    assert repr(query)  # just test this doesn't raise

    if query.was_cached:
        assert query.nb_tries == 0
        assert query.done
        assert query.error is None
        assert query.response is not None
        assert query.result_set is not None
        assert query.response_size_mib >= 0.0
        assert query.query_duration_secs is None
        assert query.run_duration_secs is None
        assert query.api_version is not None
        assert query.timestamp_osm is not None
        # query.timestamp_areas can be set or not
        return  # don't go into the other blocks

    if query.nb_tries == 0:
        assert not query.done
        assert query.error is None
        assert query.response is None
        assert query.result_set is None
        assert query.response_size_mib is None
        assert query.query_duration_secs is None
        assert query.run_duration_secs is None
        assert query.api_version is None
        assert query.timestamp_osm is None
        assert query.timestamp_areas is None

    if query.error is not None:
        assert not query.done
        assert query.nb_tries > 0
        assert query.response is None
        assert query.result_set is None
        assert query.response_size_mib is None
        assert query.query_duration_secs is None
        assert query.run_duration_secs > 0.0
        assert query.api_version is None
        assert query.timestamp_osm is None
        assert query.timestamp_areas is None

    if query.done:
        assert query.nb_tries > 0
        assert query.error is None
        assert query.response is not None
        assert query.result_set is not None
        assert query.response_size_mib >= 0.0
        assert query.query_duration_secs > 0.0
        assert query.run_duration_secs > 0.0
        assert query.api_version is not None
        assert query.timestamp_osm is not None
        # query.timestamp_areas can be set or not
