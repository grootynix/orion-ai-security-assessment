"""Deprecated compatibility shim. Import from app.persistence.store instead."""

from warnings import warn

from app.persistence.store import Store, utc_now

warn(
    "app.store is deprecated; use app.persistence.store",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["Store", "utc_now"]
