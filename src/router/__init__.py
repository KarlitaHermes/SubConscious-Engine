"""Router package."""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = ["Router"]

if TYPE_CHECKING:
    from src.router.router import Router


def __getattr__(name: str) -> type:
    if name == "Router":
        from src.router.router import Router

        return Router
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
