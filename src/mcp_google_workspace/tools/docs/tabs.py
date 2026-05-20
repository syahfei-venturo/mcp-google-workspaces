"""Tab management operations for Google Docs."""

from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import Context

from ...registry import ToolParameter, ToolRegistry
from ._utils import safe_batch_update, validate_document_id


def list_document_tabs(
    document_id: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """List all tabs in a Google Document.

    Returns tab metadata: ID, title, index, and nesting level.
    Tabs are a newer Docs feature; documents without tabs return a
    single default tab.
    """
    if err := validate_document_id(document_id):
        return err

    docs_service = ctx.request_context.lifespan_context.docs_service

    doc = (
        docs_service.documents()
        .get(
            documentId=document_id,
            includeTabsContent=False,
        )
        .execute()
    )

    raw_tabs = doc.get("tabs", [])
    tabs: List[Dict[str, Any]] = []
    for tab in raw_tabs:
        props = tab.get("tabProperties", {})
        tabs.append(
            {
                "tabId": props.get("tabId"),
                "title": props.get("title"),
                "index": props.get("index"),
                "nestingLevel": props.get("nestingLevel", 0),
            }
        )

    return {
        "documentId": document_id,
        "title": doc.get("title"),
        "tabs": tabs,
        "tabCount": len(tabs),
    }


def add_tab(
    document_id: str,
    title: Optional[str] = None,
    parent_tab_id: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Add a new tab to a Google Document.

    The tab is appended after existing tabs at the same level.
    Use parent_tab_id to create a nested child tab.
    """
    if err := validate_document_id(document_id):
        return err

    docs_service = ctx.request_context.lifespan_context.docs_service

    tab_properties: Dict[str, Any] = {}
    if title:
        tab_properties["title"] = title

    request: Dict[str, Any] = {"tabProperties": tab_properties}
    if parent_tab_id:
        request["parentTabId"] = parent_tab_id

    result = safe_batch_update(
        docs_service,
        document_id,
        [{"createTab": request}],
    )

    if "error" in result:
        return result

    # Extract created tab properties from reply
    replies = result.get("replies", [])
    created_props = {}
    if replies and "createTab" in replies[0]:
        created_props = replies[0]["createTab"].get("tabProperties", {})

    return {
        "documentId": document_id,
        "tabId": created_props.get("tabId"),
        "title": created_props.get("title", title),
        "index": created_props.get("index"),
        "nestingLevel": created_props.get("nestingLevel", 0),
    }


def rename_tab(
    document_id: str,
    tab_id: str,
    title: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Rename a tab in a Google Document."""
    if err := validate_document_id(document_id):
        return err
    if not tab_id or not tab_id.strip():
        return {"error": "tab_id must be a non-empty string"}
    if not title or not title.strip():
        return {"error": "title must be a non-empty string"}

    docs_service = ctx.request_context.lifespan_context.docs_service

    result = safe_batch_update(
        docs_service,
        document_id,
        [
            {
                "updateTabProperties": {
                    "tabProperties": {
                        "tabId": tab_id,
                        "title": title,
                    },
                    "fields": "title",
                }
            }
        ],
    )

    if "error" in result:
        return result

    return {
        "documentId": document_id,
        "tabId": tab_id,
        "title": title,
    }


def register(registry: ToolRegistry) -> None:
    """Register all Docs tab management tools in the registry."""
    registry.register(
        name="list_document_tabs",
        description=(
            "List all tabs in a Google Document. Returns tab ID, title, index, "
            "and nesting level. Documents without explicit tabs return a single "
            "default tab."
        ),
        parameters=[
            ToolParameter(
                "document_id", "string", "The ID of the document (from URL)"
            ),
        ],
        tags=["docs", "tabs", "list", "read", "sections", "pages"],
        fn=list_document_tabs,
        read_only=True,
    )

    registry.register(
        name="add_tab",
        description=(
            "Add a new tab to a Google Document. "
            "Optionally specify a title and parent_tab_id for nested tabs."
        ),
        parameters=[
            ToolParameter(
                "document_id", "string", "The ID of the document (from URL)"
            ),
            ToolParameter(
                "title",
                "string",
                "Title for the new tab. Defaults to 'Tab N' if omitted.",
                required=False,
            ),
            ToolParameter(
                "parent_tab_id",
                "string",
                "Tab ID of the parent tab for creating a nested child tab.",
                required=False,
            ),
        ],
        tags=["docs", "tabs", "add", "create", "new", "sections"],
        fn=add_tab,
    )

    registry.register(
        name="rename_tab",
        description=(
            "Rename a tab in a Google Document. "
            "Use list_document_tabs to find tab IDs."
        ),
        parameters=[
            ToolParameter(
                "document_id", "string", "The ID of the document (from URL)"
            ),
            ToolParameter(
                "tab_id",
                "string",
                "The tab ID to rename (from list_document_tabs)",
            ),
            ToolParameter("title", "string", "New title for the tab"),
        ],
        tags=["docs", "tabs", "rename", "update", "title", "sections"],
        fn=rename_tab,
    )
