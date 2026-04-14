"""Runtime checker: logs warnings for unsupported NiceGUI elements."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nicegui.element import Element


_LOGGER_NAME = "nicegui_tui"
_warned_types: set[str] = set()


def get_logger() -> logging.Logger:
    """Return the package logger. Call :func:`logging.basicConfig` first if needed."""
    logger = logging.getLogger(_LOGGER_NAME)
    return logger


def warn_unsupported(element: "Element") -> None:
    """Emit a one-time WARN log for an unsupported element type."""
    type_name = type(element).__name__
    if type_name in _warned_types:
        return
    _warned_types.add(type_name)
    get_logger().warning(
        "Element type %r is not supported by nicegui-tui; rendering placeholder.",
        type_name,
    )


def reset_warnings() -> None:
    """For tests: clear the dedupe set so warnings are re-emitted."""
    _warned_types.clear()
