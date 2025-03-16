import os
from typing import Final


__docformat__ = "google"
__all__ = (
    "IS_CI",
    "IS_UNIT_TEST",
    "FORCE_DISABLE_CACHE",
)

IS_CI: Final[bool] = "GITHUB_ACTIONS" in os.environ
IS_UNIT_TEST: Final[bool] = "PYTEST_VERSION" in os.environ
FORCE_DISABLE_CACHE: Final[bool] = IS_CI and not IS_UNIT_TEST
