"""Tool registration for Google Sheets operations."""

from ...registry import ToolRegistry
from . import charts, comments, format, manage, read, write


def register(registry: ToolRegistry) -> None:
    """Register all Sheets tools into the registry."""
    read.register(registry)
    write.register(registry)
    manage.register(registry)
    charts.register(registry)
    format.register(registry)
    comments.register(registry)
    registry.set_category("sheets")
