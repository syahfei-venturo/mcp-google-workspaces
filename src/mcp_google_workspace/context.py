"""Context dataclasses for Google Workspace services."""

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class WorkspaceContext:
    """Top-level context holding all Google Workspace service clients.

    Yielded by the lifespan manager and accessible in tool functions
    via ``ctx.request_context.lifespan_context``.
    """

    sheets_service: Any
    docs_service: Any
    drive_service: Any
    folder_id: Optional[str] = None
