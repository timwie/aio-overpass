"""Async client for the Overpass API."""

__version__ = "0.4.0"

# we add this to all modules for pdoc;
# see https://pdoc.dev/docs/pdoc.html#use-numpydoc-or-google-docstrings
__docformat__ = "google"

# we also use __all__ in all modules for pdoc; this lets us control the order
__all__ = (
    "Client",
    "ClientError",
    "Query",
    "client",
    "element",
    "error",
    "pt",
    "pt_ordered",
    "query",
)

from .client import Client
from .error import ClientError
from .query import Query
