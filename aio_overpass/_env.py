import os
from typing import Final


IS_CI: Final[bool] = "GITHUB_ACTIONS" in os.environ
IS_UNIT_TEST: Final[bool] = "PYTEST_VERSION" in os.environ
FORCE_DISABLE_CACHE: Final[bool] = IS_CI and not IS_UNIT_TEST
