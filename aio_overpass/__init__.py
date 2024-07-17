"""
Async client for the Overpass API.

[Release Notes](https://github.com/timwie/aio-overpass/blob/main/RELEASES.md)

[Examples](https://github.com/timwie/aio-overpass/tree/main/examples)
"""

import importlib.metadata
from pathlib import Path


__version__: str = importlib.metadata.version("aio-overpass")

# we add this to all modules for pdoc;
# see https://pdoc.dev/docs/pdoc.html#use-numpydoc-or-google-docstrings
__docformat__ = "google"

# we also use __all__ in all modules for pdoc; this lets us control the order
__all__ = (
    "__version__",
    "Client",
    "ClientError",
    "Query",
    "client",
    "element",
    "error",
    "pt",
    "pt_ordered",
    "ql",
    "query",
    "spatial",
)

from .client import Client
from .error import ClientError
from .query import Query


# extend the module's docstring
for filename in ("usage.md", "extras.md", "coordinates.md"):
    __doc__ += "\n<br>\n"
    __doc__ += (Path(__file__).parent / "doc" / filename).read_text()
