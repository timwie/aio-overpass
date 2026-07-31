import os
import subprocess
import sys
import textwrap

import pytest


# The unit test suite runs against ``_ClockMock``, so the clock that is actually shipped
# is only reachable from a subprocess that does not look like a pytest run.
_SCRIPT = textwrap.dedent(
    """
    from aio_overpass._clock import Instant, monotonic
    from aio_overpass._env import IS_UNIT_TEST

    assert not IS_UNIT_TEST, "this script must not use the mocked clock"

    # There is no event loop in this thread, which is the state every synchronous
    # caller of the library is in. Reading the clock must work regardless.
    earlier = Instant.now()
    assert monotonic() > 0.0
    assert earlier.elapsed_secs_since >= 0.0
    """
)


@pytest.mark.xdist_group(name="fast")
def test_clock_does_not_require_an_event_loop():
    env = {k: v for k, v in os.environ.items() if k != "PYTEST_VERSION"}

    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", _SCRIPT],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
