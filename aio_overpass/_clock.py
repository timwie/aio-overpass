import asyncio
import math
import time
from dataclasses import dataclass

from aio_overpass._env import IS_UNIT_TEST


__docformat__ = "google"
__all__ = (
    "sleep",
    "monotonic",
    "Instant",
)


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
    monotonic = _clock_mock.mock_time
else:  # pragma: no cover
    sleep = asyncio.sleep
    # This is the clock ``loop.time()`` reads, but it does not require a current event
    # loop: since Python 3.14, ``asyncio.get_event_loop()`` raises a RuntimeError when
    # called outside a running loop, instead of implicitly creating one.
    monotonic = time.monotonic


@dataclass(kw_only=True, slots=True, frozen=True, repr=False, order=True)
class Instant:
    """
    Measurement of a monotonic clock.

    Attributes:
        when: the current time, according to a monotonic clock
              (the same one used by the event loop; details are unspecified).
    """

    when: float

    @classmethod
    def now(cls) -> "Instant":
        return cls(when=monotonic())

    @property
    def ceil(self) -> int:
        return math.ceil(self.when)

    @property
    def elapsed_secs_since(self) -> float:
        return monotonic() - self.when

    def __sub__(self, earlier: "Instant") -> float:
        if self.when < earlier.when:
            msg = f"{self} is earlier than {earlier}"
            raise ArithmeticError(msg)
        return self.when - earlier.when

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.when:.02f})"
