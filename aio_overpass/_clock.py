import asyncio
import math
from dataclasses import dataclass

from aio_overpass._env import IS_UNIT_TEST


class _ClockMock:
    """Mock alternative to event loop time."""

    __slots__ = ("_time",)

    def __init__(self) -> None:
        self._time = 0.0

    async def mock_sleep(self, delay: float) -> None:
        self._time += delay
        await asyncio.sleep(0.0)

    def mock_time(self) -> float:
        return self._time


if IS_UNIT_TEST:
    _clock_mock = _ClockMock()
    sleep = _clock_mock.mock_sleep
    time = _clock_mock.mock_time
else:
    sleep = asyncio.sleep
    time = asyncio.get_event_loop().time


@dataclass(kw_only=True, slots=True, frozen=True, repr=False, order=True)
class Instant:
    """
    Measurement of a monotonic clock.

    Attributes:
        when: the current time, according to the event loop's internal monotonic clock
              (details are unspecified and may differ per event loop).
    """

    when: float

    @classmethod
    def now(cls) -> "Instant":
        return cls(when=time())

    @property
    def ceil(self) -> int:
        return math.ceil(self.when)

    @property
    def elapsed_secs_since(self) -> float:
        return time() - self.when

    def __sub__(self, earlier: "Instant") -> float:
        if self.when < earlier.when:
            msg = f"{self} is earlier than {earlier}"
            raise ValueError(msg)
        return self.when - earlier.when

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.when:.02f})"
