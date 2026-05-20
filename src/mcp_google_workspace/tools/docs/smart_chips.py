"""Smart chip insertion for Google Docs."""

import re
from typing import Any, Dict, Optional

from mcp.server.fastmcp import Context

from ...registry import ToolParameter, ToolRegistry
from ._utils import safe_batch_update, validate_document_id, validate_uri

# RFC 5322 simplified email pattern — covers the vast majority of valid addresses
_EMAIL_PATTERN = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$"
)


def insert_rich_link(
    document_id: str,
    uri: str,
    index: int = 1,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Insert a rich link (smart chip) at a position in a Google Document.

    Rich links display an interactive preview card for URLs — Google Drive
    files, YouTube videos, Maps locations, and other supported URLs render
    as smart chips instead of plain hyperlinks.
    """
    if err := validate_document_id(document_id):
        return err
    if err := validate_uri(uri):
        return err

    docs_service = ctx.request_context.lifespan_context.docs_service

    result = safe_batch_update(
        docs_service,
        document_id,
        [{"insertRichLink": {"uri": uri, "location": {"index": index}}}],
    )

    if "error" in result:
        return result

    return {
        "documentId": document_id,
        "insertedAt": index,
        "uri": uri,
        "replies": result.get("replies", []),
    }


def insert_person_chip(
    document_id: str,
    email: str,
    index: int = 1,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Insert a person smart chip (mention) at a position in a Google Document.

    Inserts a rich link chip using the person's Google account email.
    The chip displays their name as an interactive element linked to
    their Google profile.
    """
    if err := validate_document_id(document_id):
        return err
    if not email or not email.strip():
        return {"error": "email must be a non-empty string"}
    if not _EMAIL_PATTERN.match(email.strip()):
        return {"error": "email must be a valid email address (e.g. user@domain.com)"}

    docs_service = ctx.request_context.lifespan_context.docs_service

    # Person chips use the Google people URI scheme
    person_uri = f"mailto:{email.strip()}"

    result = safe_batch_update(
        docs_service,
        document_id,
        [{"insertRichLink": {"uri": person_uri, "location": {"index": index}}}],
    )

    if "error" in result:
        return result

    return {
        "documentId": document_id,
        "insertedAt": index,
        "type": "personChip",
        "email": email.strip(),
        "replies": result.get("replies", []),
    }


def list_smart_chips(
    document_id: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """List all smart chips (rich links, person mentions) in a Google Document.

    Scans the document body for richLink elements and returns their
    positions, URIs, titles, and MIME types.
    """
    if err := validate_document_id(document_id):
        return err

    docs_service = ctx.request_context.lifespan_context.docs_service

    doc = docs_service.documents().get(documentId=document_id).execute()
    body = doc.get("body", {})
    content = body.get("content", [])

    chips = []
    for element in content:
        paragraph = element.get("paragraph")
        if not paragraph:
            continue
        for pe in paragraph.get("elements", []):
            rich_link = pe.get("richLink")
            if rich_link:
                props = rich_link.get("richLinkProperties", {})
                chips.append(
                    {
                        "startIndex": pe.get("startIndex"),
                        "endIndex": pe.get("endIndex"),
                        "uri": props.get("uri"),
                        "title": props.get("title"),
                        "mimeType": props.get("mimeType"),
                    }
                )

    return {
        "documentId": document_id,
        "title": doc.get("title"),
        "smartChips": chips,
        "count": len(chips),
    }


def register(registry: ToolRegistry) -> None:
    """Register all Docs smart chip tools in the registry."""
    registry.register(
        name="insert_rich_link",
        description=(
            "Insert a rich link (smart chip) at a position in a Google Document. "
            "Supported URLs render as interactive preview chips: Google Drive files, "
            "YouTube videos, Maps, and other Google services. "
            "Use get_text_with_indices to find the right insertion index."
        ),
        parameters=[
            ToolParameter(
                "document_id", "string", "The ID of the document (from URL)"
            ),
            ToolParameter("uri", "string", "HTTPS URL to insert as a rich link chip"),
            ToolParameter(
                "index",
                "integer",
                "Character index to insert at (1 = start of body, default: 1)",
                required=False,
                default=1,
            ),
        ],
        tags=["docs", "rich", "link", "chip", "smart", "insert", "embed", "url"],
        fn=insert_rich_link,
    )

    registry.register(
        name="insert_person_chip",
        description=(
            "Insert a person smart chip (mention) at a position in a Google Document. "
            "Displays the person as an interactive inline chip. "
            "Requires a valid Google account email address."
        ),
        parameters=[
            ToolParameter(
                "document_id", "string", "The ID of the document (from URL)"
            ),
            ToolParameter(
                "email",
                "string",
                "Google account email address of the person to mention",
            ),
            ToolParameter(
                "index",
                "integer",
                "Character index to insert at (1 = start of body, default: 1)",
                required=False,
                default=1,
            ),
        ],
        tags=["docs", "person", "chip", "smart", "mention", "insert", "people"],
        fn=insert_person_chip,
    )

    registry.register(
        name="list_smart_chips",
        description=(
            "List all smart chips (rich links, person mentions) in a Google Document. "
            "Returns position, URI, title, and MIME type for each chip found."
        ),
        parameters=[
            ToolParameter(
                "document_id", "string", "The ID of the document (from URL)"
            ),
        ],
        tags=["docs", "smart", "chips", "list", "rich", "links", "read", "find"],
        fn=list_smart_chips,
        read_only=True,
    )
