"""Async client for the Overpass API."""
import importlib.metadata


__version__: str = importlib.metadata.version("aio-overpass")

# we add this to all modules for pdoc;
# see https://pdoc.dev/docs/pdoc.html#use-numpydoc-or-google-docstrings
__docformat__ = "google"

# we also use __all__ in all modules for pdoc; this lets us control the order
__all__ = (
    "Client",
    "ClientError",
    "Query",
    "client",
    "element",  # pyright: ignore[reportUnsupportedDunderAll]
    "error",
    "pt",  # pyright: ignore[reportUnsupportedDunderAll]
    "pt_ordered",  # pyright: ignore[reportUnsupportedDunderAll]
    "ql",  # pyright: ignore[reportUnsupportedDunderAll]
    "query",
)

from .client import Client
from .error import ClientError
from .query import Query
