from aio_overpass import Query
from aio_overpass.query import DefaultQueryRunner, QueryRunner


class VerifyingQueryRunner(QueryRunner):
    """
    Same as the default runner, but with calls to ``verify_query_state()``
    before and after yielding to it.
    """

    def __init__(self, *args, **kwargs) -> None:
        self._default = DefaultQueryRunner(*args, **kwargs)

    async def __call__(self, query: Query) -> None:
        verify_query_state(query)
        await self._default(query)
        verify_query_state(query)


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

    if query.nb_tries == 0:
        assert not query.done
        assert query.error is None
        assert query.result_set is None
        assert query.result_size_mib is None
        assert query.query_duration_secs is None
        assert query.run_duration_secs is None
        assert query.api_version is None
        assert query.timestamp_osm is None
        assert query.timestamp_areas is None

    if query.error is not None:
        assert not query.done
        assert query.nb_tries > 0
        assert query.result_set is None
        assert query.result_size_mib is None
        assert query.query_duration_secs is None
        assert query.run_duration_secs > 0.0
        assert query.api_version is None
        assert query.timestamp_osm is None
        assert query.timestamp_areas is None

    if query.done:
        assert query.nb_tries > 0
        assert query.error is None
        assert query.result_set is not None
        assert query.result_size_mib >= 0.0
        assert query.query_duration_secs > 0.0
        assert query.run_duration_secs > 0.0
        assert query.api_version is not None
        assert query.timestamp_osm is not None
        # query.timestamp_areas can be set or not
