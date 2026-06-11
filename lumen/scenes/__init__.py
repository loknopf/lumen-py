"""Importing this package registers every scene via the ``@register`` decorator.

Add a new scene by dropping a module in here and importing it below.
"""

from . import clock, countdown, github, idle, transit, weather  # noqa: F401

__all__ = ["weather", "transit", "github", "countdown", "idle", "clock"]
