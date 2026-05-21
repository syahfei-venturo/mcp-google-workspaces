"""Tool registration for Google Docs operations."""

from ...registry import ToolRegistry
from . import comments, format, manage, read, smart_chips, table, tabs, write


def register(registry: ToolRegistry) -> None:
    """Register all Docs tools into the registry."""
    read.register(registry)
    write.register(registry)
    format.register(registry)
    manage.register(registry)
    table.register(registry)
    comments.register(registry)
    tabs.register(registry)
    smart_chips.register(registry)
    registry.set_category("docs")
