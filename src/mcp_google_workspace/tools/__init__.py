"""Tool registration for all Google Workspace operations."""

from typing import Optional, Set

from ..registry import ToolRegistry
from . import docs, sheets


def register_all_tools(
    registry: ToolRegistry,
    enabled_tools: Optional[Set[str]] = None,
) -> None:
    """Register all tools from all services into the registry.

    Args:
        registry: The tool registry to populate
        enabled_tools: If provided, only keep tools in this set after registration
    """
    sheets.register(registry)
    docs.register(registry)

    if enabled_tools is not None:
        registry.filter(enabled_tools)
