"""Importing this package registers every scene via the ``@register`` decorator.

Add a new scene by dropping a module in here and importing it below.
"""

from . import clock, countdown, github, idle, status, transit, weather  # noqa: F401

__all__ = ["weather", "transit", "github", "status", "countdown", "idle", "clock"]
