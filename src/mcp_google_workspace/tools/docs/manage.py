"""Document management operations for Google Docs."""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from googleapiclient.errors import HttpError
from googleapiclient.http import MediaInMemoryUpload
from mcp.server.fastmcp import Context

from ...registry import ToolParameter, ToolRegistry
from ...utils.common import drive_create_with_fallback, escape_drive_value
from ._utils import safe_batch_update, validate_document_id

logger = logging.getLogger(__name__)

# Maximum HTML content size (5 MB)
MAX_HTML_BYTES = 5 * 1024 * 1024


def create_document_from_html(
    title: str,
    html_content: str,
    folder_id: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Create a new Google Document from HTML content.

    Uses the Drive API media upload to convert HTML into a native
    Google Document.  Supports rich formatting including headings,
    tables, lists, bold/italic, links, and images.

    This creates a **new** document — it cannot inject HTML into an
    existing document (Drive API limitation).
    """
    if not title or not title.strip():
        return {"error": "title must be a non-empty string"}
    if not html_content or not html_content.strip():
        return {"error": "html_content must be a non-empty string"}

    html_bytes = html_content.encode("utf-8")
    if len(html_bytes) > MAX_HTML_BYTES:
        return {
            "error": (
                f"HTML content exceeds maximum size "
                f"({len(html_bytes):,} bytes > {MAX_HTML_BYTES:,} bytes)"
            )
        }

    drive_service = ctx.request_context.lifespan_context.drive_service
    target_folder_id = folder_id or ctx.request_context.lifespan_context.folder_id

    file_body: Dict[str, Any] = {
        "name": title,
        "mimeType": "application/vnd.google-apps.document",
    }
    if target_folder_id:
        file_body["parents"] = [target_folder_id]

    media = MediaInMemoryUpload(html_bytes, mimetype="text/html")

    try:
        document, warning = drive_create_with_fallback(
            drive_service, file_body, media_body=media
        )
    except Exception as e:
        return {"error": f"Failed to create document from HTML: {e}"}

    parents = document.get("parents")
    result: Dict[str, Any] = {
        "documentId": document.get("id"),
        "title": document.get("name", title),
        "folder": parents[0] if parents else "root",
    }
    if warning:
        result["warning"] = warning
    return result


def overwrite_document_from_html(
    document_id: str,
    html_content: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Overwrite the entire body of an existing Google Document with HTML.

    Uses the Drive API media upload to replace all content while
    preserving document ID, sharing settings, and comments.
    """
    if err := validate_document_id(document_id):
        return err
    if not html_content or not html_content.strip():
        return {"error": "html_content must be a non-empty string"}

    html_bytes = html_content.encode("utf-8")
    if len(html_bytes) > MAX_HTML_BYTES:
        return {
            "error": (
                f"HTML content exceeds maximum size "
                f"({len(html_bytes):,} bytes > {MAX_HTML_BYTES:,} bytes)"
            )
        }

    drive_service = ctx.request_context.lifespan_context.drive_service

    media = MediaInMemoryUpload(html_bytes, mimetype="text/html")

    try:
        result = (
            drive_service.files()
            .update(
                fileId=document_id,
                media_body=media,
                supportsAllDrives=True,
                fields="id, name",
            )
            .execute()
        )
    except Exception as e:
        return {"error": f"Failed to overwrite document: {e}"}

    return {
        "documentId": result.get("id", document_id),
        "title": result.get("name", ""),
        "status": "overwritten",
    }


def append_html(
    document_id: str,
    html_content: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Append HTML content to the end of an existing Google Document.

    Exports the current document as HTML, inserts new content before
    the closing ``</body>`` tag, and overwrites via Drive API media upload.
    Preserves document ID, sharing settings, and comments.
    """
    if err := validate_document_id(document_id):
        return err
    if not html_content or not html_content.strip():
        return {"error": "html_content must be a non-empty string"}

    drive_service = ctx.request_context.lifespan_context.drive_service

    # Export current document as HTML
    try:
        current_html_bytes = (
            drive_service.files()
            .export(fileId=document_id, mimeType="text/html")
            .execute()
        )
        current_html = current_html_bytes.decode("utf-8")
    except Exception as e:
        return {"error": f"Failed to export document as HTML: {e}"}

    # Insert new HTML before </body>
    match = re.search(r"</body>", current_html, re.IGNORECASE)
    if match:
        insert_pos = match.start()
        combined = current_html[:insert_pos] + html_content + current_html[insert_pos:]
    else:
        combined = current_html + html_content

    combined_bytes = combined.encode("utf-8")
    if len(combined_bytes) > MAX_HTML_BYTES:
        return {
            "error": (
                f"Combined HTML exceeds maximum size "
                f"({len(combined_bytes):,} bytes > {MAX_HTML_BYTES:,} bytes)"
            )
        }

    media = MediaInMemoryUpload(combined_bytes, mimetype="text/html")

    try:
        result = (
            drive_service.files()
            .update(
                fileId=document_id,
                media_body=media,
                supportsAllDrives=True,
                fields="id, name",
            )
            .execute()
        )
    except Exception as e:
        return {"error": f"Failed to update document: {e}"}

    return {
        "documentId": result.get("id", document_id),
        "title": result.get("name", ""),
        "status": "appended",
        "appendedLength": len(html_content),
    }


def create_document(
    title: str,
    folder_id: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Create a new Google Document."""
    if not title or not title.strip():
        return {"error": "title must be a non-empty string"}

    drive_service = ctx.request_context.lifespan_context.drive_service
    target_folder_id = folder_id or ctx.request_context.lifespan_context.folder_id

    file_body: Dict[str, Any] = {
        "name": title,
        "mimeType": "application/vnd.google-apps.document",
    }
    if target_folder_id:
        file_body["parents"] = [target_folder_id]

    try:
        document, warning = drive_create_with_fallback(drive_service, file_body)
    except Exception as e:
        return {"error": f"Failed to create document: {e}"}

    parents = document.get("parents")
    result: Dict[str, Any] = {
        "documentId": document.get("id"),
        "title": document.get("name", title),
        "folder": parents[0] if parents else "root",
    }
    if warning:
        result["warning"] = warning
    return result


def delete_document(
    document_id: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Move a Google Document to trash."""
    if err := validate_document_id(document_id):
        return err

    drive_service = ctx.request_context.lifespan_context.drive_service

    drive_service.files().update(
        fileId=document_id,
        supportsAllDrives=True,
        body={"trashed": True},
    ).execute()

    return {
        "documentId": document_id,
        "status": "trashed",
    }


def list_documents(
    folder_id: Optional[str] = None,
    max_results: int = 20,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """List Google Documents in a Drive folder."""
    drive_service = ctx.request_context.lifespan_context.drive_service
    target_folder_id = folder_id or ctx.request_context.lifespan_context.folder_id
    max_results = min(max(1, max_results), 100)

    warning: Optional[str] = None
    query = "mimeType='application/vnd.google-apps.document'"
    if target_folder_id:
        query += f" and '{escape_drive_value(target_folder_id)}' in parents"

    def _list(q: str) -> Dict[str, Any]:
        return (
            drive_service.files()
            .list(
                q=q,
                pageSize=max_results,
                spaces="drive",
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
                fields="files(id, name, createdTime, modifiedTime, owners, webViewLink)",
                orderBy="modifiedTime desc",
            )
            .execute()
        )

    try:
        results = _list(query)
    except HttpError as e:
        if e.resp.status == 404 and target_folder_id:
            warning = (
                f"Folder '{target_folder_id}' not found — listing My Drive root instead. "
                f"Update DRIVE_FOLDER_ID to a valid folder ID."
            )
            fallback_query = "mimeType='application/vnd.google-apps.document'"
            results = _list(fallback_query)
        else:
            return {"error": f"Failed to list documents: {e}", "items": []}

    items = [
        {
            "id": f["id"],
            "name": f["name"],
            "created_time": f.get("createdTime"),
            "modified_time": f.get("modifiedTime"),
            "owners": [o.get("emailAddress") for o in f.get("owners", [])],
            "web_link": f.get("webViewLink"),
        }
        for f in results.get("files", [])
    ]

    result: Dict[str, Any] = {"items": items}
    if warning:
        result["warning"] = warning
    return result


def share_document(
    document_id: str,
    recipients: List[Dict[str, str]],
    send_notification: bool = True,
    ctx: Optional[Context] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Share a Google Document with users via email."""
    drive_service = ctx.request_context.lifespan_context.drive_service
    successes: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []

    for recipient in recipients:
        email_address = recipient.get("email_address")
        role = recipient.get("role", "writer")

        if not email_address:
            failures.append({"email_address": None, "error": "Missing email_address"})
            continue
        if role not in ["reader", "commenter", "writer"]:
            failures.append(
                {
                    "email_address": email_address,
                    "error": f"Invalid role '{role}'",
                }
            )
            continue

        try:
            result = (
                drive_service.permissions()
                .create(
                    fileId=document_id,
                    body={
                        "type": "user",
                        "role": role,
                        "emailAddress": email_address,
                    },
                    sendNotificationEmail=send_notification,
                    fields="id",
                )
                .execute()
            )
            successes.append(
                {
                    "email_address": email_address,
                    "role": role,
                    "permissionId": result.get("id"),
                }
            )
        except Exception as e:
            if isinstance(e, HttpError):
                try:
                    error_content = json.loads(e.content)
                    error_details = error_content.get("error", {}).get(
                        "message", str(e)
                    )
                except (json.JSONDecodeError, AttributeError):
                    error_details = str(e)
            else:
                error_details = "Permission denied or invalid request"
            failures.append(
                {
                    "email_address": email_address,
                    "error": f"Failed to share: {error_details}",
                }
            )

    return {"successes": successes, "failures": failures}


def create_header(
    document_id: str,
    section_type: str = "DEFAULT",
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Create a header in the document.

    ``section_type`` can be ``DEFAULT`` (all pages) or
    ``FIRST`` (first page only — requires
    ``useFirstPageHeaderFooter`` enabled on the document style).
    """
    if err := validate_document_id(document_id):
        return err

    upper = section_type.upper()
    if upper not in ("DEFAULT", "FIRST"):
        return {
            "error": (
                f"Invalid section_type '{section_type}'. Must be DEFAULT or FIRST"
            )
        }

    docs_service = ctx.request_context.lifespan_context.docs_service

    request_body: Dict[str, Any] = {
        "type": upper,
    }
    # DEFAULT → no sectionBreakLocation needed (applies to first section)
    requests = [{"createHeader": request_body}]

    result = safe_batch_update(docs_service, document_id, requests)
    if "error" in result:
        return result

    header_id = None
    for reply in result.get("replies", []):
        header_id = reply.get("createHeader", {}).get("headerId")

    return {
        "documentId": document_id,
        "headerId": header_id,
        "sectionType": upper,
    }


def create_footer(
    document_id: str,
    section_type: str = "DEFAULT",
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Create a footer in the document.

    ``section_type`` can be ``DEFAULT`` (all pages) or
    ``FIRST`` (first page only).
    """
    if err := validate_document_id(document_id):
        return err

    upper = section_type.upper()
    if upper not in ("DEFAULT", "FIRST"):
        return {
            "error": (
                f"Invalid section_type '{section_type}'. Must be DEFAULT or FIRST"
            )
        }

    docs_service = ctx.request_context.lifespan_context.docs_service

    requests = [{"createFooter": {"type": upper}}]

    result = safe_batch_update(docs_service, document_id, requests)
    if "error" in result:
        return result

    footer_id = None
    for reply in result.get("replies", []):
        footer_id = reply.get("createFooter", {}).get("footerId")

    return {
        "documentId": document_id,
        "footerId": footer_id,
        "sectionType": upper,
    }


def delete_header(
    document_id: str,
    header_id: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Delete a header by its ID."""
    if err := validate_document_id(document_id):
        return err
    if not header_id or not header_id.strip():
        return {"error": "header_id must be a non-empty string"}

    docs_service = ctx.request_context.lifespan_context.docs_service

    requests = [{"deleteHeader": {"headerId": header_id}}]

    result = safe_batch_update(docs_service, document_id, requests)
    if "error" in result:
        return result

    return {
        "documentId": document_id,
        "deletedHeaderId": header_id,
    }


def delete_footer(
    document_id: str,
    footer_id: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Delete a footer by its ID."""
    if err := validate_document_id(document_id):
        return err
    if not footer_id or not footer_id.strip():
        return {"error": "footer_id must be a non-empty string"}

    docs_service = ctx.request_context.lifespan_context.docs_service

    requests = [{"deleteFooter": {"footerId": footer_id}}]

    result = safe_batch_update(docs_service, document_id, requests)
    if "error" in result:
        return result

    return {
        "documentId": document_id,
        "deletedFooterId": footer_id,
    }


def create_named_range(
    document_id: str,
    name: str,
    start_index: int,
    end_index: int,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Create a named range spanning the given character indices.

    Named ranges act as bookmarks that tools and scripts can
    reference by name instead of fragile character offsets.
    """
    if err := validate_document_id(document_id):
        return err
    if not name or not name.strip():
        return {"error": "name must be a non-empty string"}
    if len(name) > 255:
        return {"error": "name must not exceed 255 characters"}
    if start_index >= end_index:
        return {"error": "start_index must be less than end_index"}

    docs_service = ctx.request_context.lifespan_context.docs_service

    requests = [
        {
            "createNamedRange": {
                "name": name,
                "range": {
                    "startIndex": start_index,
                    "endIndex": end_index,
                },
            }
        }
    ]

    result = safe_batch_update(docs_service, document_id, requests)
    if "error" in result:
        return result

    named_range_id = None
    for reply in result.get("replies", []):
        named_range_id = reply.get("createNamedRange", {}).get("namedRangeId")

    return {
        "documentId": document_id,
        "namedRangeId": named_range_id,
        "name": name,
        "range": {"startIndex": start_index, "endIndex": end_index},
    }


def delete_named_range(
    document_id: str,
    named_range_id: Optional[str] = None,
    name: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Delete a named range by ID or by name.

    Provide either ``named_range_id`` or ``name``.
    If ``name`` is given, all ranges with that name are deleted.
    """
    if err := validate_document_id(document_id):
        return err
    if not named_range_id and not name:
        return {"error": "Provide either named_range_id or name"}

    docs_service = ctx.request_context.lifespan_context.docs_service

    request: Dict[str, Any] = {}
    if named_range_id:
        request["namedRangeId"] = named_range_id
    else:
        request["name"] = name

    requests = [{"deleteNamedRange": request}]

    result = safe_batch_update(docs_service, document_id, requests)
    if "error" in result:
        return result

    return {
        "documentId": document_id,
        "deleted": named_range_id or name,
    }


def replace_named_range_content(
    document_id: str,
    text: str,
    named_range_id: Optional[str] = None,
    name: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Replace the content of a named range with new text.

    Provide either ``named_range_id`` or ``name`` to identify
    the target range.  If ``name`` is given, all ranges with
    that name are updated.
    """
    if err := validate_document_id(document_id):
        return err
    if not named_range_id and not name:
        return {"error": "Provide either named_range_id or name"}

    docs_service = ctx.request_context.lifespan_context.docs_service

    request: Dict[str, Any] = {"text": text}
    if named_range_id:
        request["namedRangeId"] = named_range_id
    else:
        request["namedRangeName"] = name

    requests = [{"replaceNamedRangeContent": request}]

    result = safe_batch_update(docs_service, document_id, requests)
    if "error" in result:
        return result

    return {
        "documentId": document_id,
        "target": named_range_id or name,
        "replacedWith": text,
        "replies": result.get("replies", []),
    }


def search_documents(
    query: str,
    folder_id: Optional[str] = None,
    page_token: Optional[str] = None,
    max_results: int = 20,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Search for Google Documents in Drive by name or content."""
    if not query or not query.strip():
        return {"error": "query must be a non-empty string"}

    drive_service = ctx.request_context.lifespan_context.drive_service
    max_results = min(max(1, max_results), 100)

    safe_query = escape_drive_value(query)
    search_query = (
        f"mimeType='application/vnd.google-apps.document' and "
        f"(name contains '{safe_query}' or fullText contains '{safe_query}')"
    )
    if folder_id:
        search_query += (
            f" and '{escape_drive_value(folder_id)}' in parents"
        )

    list_kwargs: Dict[str, Any] = {
        "q": search_query,
        "pageSize": max_results,
        "spaces": "drive",
        "includeItemsFromAllDrives": True,
        "supportsAllDrives": True,
        "fields": (
            "nextPageToken, "
            "files(id, name, createdTime, modifiedTime, owners, webViewLink)"
        ),
        "orderBy": "modifiedTime desc",
    }
    if page_token:
        list_kwargs["pageToken"] = page_token

    results = (
        drive_service.files()
        .list(**list_kwargs)
        .execute()
    )

    items = [
        {
            "id": f["id"],
            "name": f["name"],
            "created_time": f.get("createdTime"),
            "modified_time": f.get("modifiedTime"),
            "owners": [o.get("emailAddress") for o in f.get("owners", [])],
            "web_link": f.get("webViewLink"),
        }
        for f in results.get("files", [])
    ]

    return {
        "items": items,
        "next_page_token": results.get("nextPageToken"),
    }


def register(registry: ToolRegistry) -> None:
    """Register all Docs management tools in the registry."""
    registry.register(
        name="create_document",
        description="Create a new Google Document in the configured Drive folder.",
        parameters=[
            ToolParameter("title", "string", "Title for the new document"),
            ToolParameter(
                "folder_id",
                "string",
                "Drive folder ID. Uses default if omitted.",
                required=False,
            ),
        ],
        tags=["docs", "create", "document", "new", "drive"],
        fn=create_document,
    )

    registry.register(
        name="create_document_from_html",
        description=(
            "Create a new Google Document from HTML content. "
            "Supports rich formatting: headings, tables, lists, bold/italic, "
            "links, images. Creates a NEW document (cannot inject into existing). "
            "Use this instead of multiple insert/format calls for complex documents."
        ),
        parameters=[
            ToolParameter("title", "string", "Title for the new document"),
            ToolParameter(
                "html_content",
                "string",
                "HTML content to convert into the document. "
                "Supports standard HTML tags: h1-h6, p, table, ul, ol, "
                "li, b, i, a, img, br, hr, etc.",
            ),
            ToolParameter(
                "folder_id",
                "string",
                "Drive folder ID. Uses default if omitted.",
                required=False,
            ),
        ],
        tags=[
            "docs", "create", "document", "html", "rich", "format",
            "convert", "table", "report", "template", "drive",
        ],
        fn=create_document_from_html,
    )

    registry.register(
        name="overwrite_document_from_html",
        description=(
            "Overwrite the entire body of an existing Google Document "
            "with HTML content. Preserves document ID, sharing settings, "
            "and comments. Use this for reliable rich-text updates to "
            "existing documents."
        ),
        parameters=[
            ToolParameter(
                "document_id",
                "string",
                "The ID of the document (from URL)",
            ),
            ToolParameter(
                "html_content",
                "string",
                "HTML content to replace all document content with. "
                "Supports standard HTML tags: h1-h6, p, table, ul, ol, "
                "li, b, i, a, img, br, hr, etc.",
            ),
        ],
        tags=[
            "docs", "overwrite", "html", "replace", "update", "content",
            "format", "rich", "rewrite", "edit", "full", "body",
        ],
        fn=overwrite_document_from_html,
    )

    registry.register(
        name="append_html",
        description=(
            "Append HTML content to the end of an existing Google Document. "
            "Preserves existing content, sharing settings, and comments. "
            "Supports rich formatting: headings, tables, lists, bold/italic, "
            "links, images."
        ),
        parameters=[
            ToolParameter(
                "document_id",
                "string",
                "The ID of the document (from URL)",
            ),
            ToolParameter(
                "html_content",
                "string",
                "HTML content to append. Supports standard HTML tags: "
                "h1-h6, p, table, ul, ol, li, b, i, a, img, br, hr, etc.",
            ),
        ],
        tags=[
            "docs", "append", "html", "add", "content", "update",
            "extend", "insert", "text", "rich", "format",
        ],
        fn=append_html,
    )

    registry.register(
        name="delete_document",
        description="Move a Google Document to trash.",
        parameters=[
            ToolParameter(
                "document_id",
                "string",
                "The ID of the document (from URL)",
            ),
        ],
        tags=["docs", "delete", "document", "trash", "remove"],
        fn=delete_document,
    )

    registry.register(
        name="list_documents",
        description="List Google Documents in a Drive folder.",
        parameters=[
            ToolParameter(
                "folder_id",
                "string",
                "Drive folder ID. Uses default if omitted.",
                required=False,
            ),
            ToolParameter(
                "max_results",
                "integer",
                "Max results (default: 20, max: 100)",
                required=False,
                default=20,
            ),
        ],
        tags=["docs", "list", "documents", "drive", "browse", "files"],
        fn=list_documents,
        read_only=True,
    )

    registry.register(
        name="search_documents",
        description=(
            "Search for Google Documents in Drive by name or content. "
            "Supports pagination via page_token for large result sets."
        ),
        parameters=[
            ToolParameter(
                "query",
                "string",
                "Search query string (searches name and content)",
            ),
            ToolParameter(
                "folder_id",
                "string",
                "Restrict search to a specific Drive folder.",
                required=False,
            ),
            ToolParameter(
                "page_token",
                "string",
                "Token for fetching the next page of results.",
                required=False,
            ),
            ToolParameter(
                "max_results",
                "integer",
                "Max results per page (default: 20, max: 100)",
                required=False,
                default=20,
            ),
        ],
        tags=["docs", "search", "find", "documents", "drive", "query"],
        fn=search_documents,
        read_only=True,
    )

    registry.register(
        name="share_document",
        description=(
            "Share a Google Document with users via email "
            "with specified roles (reader/commenter/writer)."
        ),
        parameters=[
            ToolParameter(
                "document_id",
                "string",
                "The ID of the document (from URL)",
            ),
            ToolParameter(
                "recipients",
                "array",
                "List of {email_address, role} objects. Role: reader/commenter/writer.",
            ),
            ToolParameter(
                "send_notification",
                "boolean",
                "Send email notification (default: true)",
                required=False,
                default=True,
            ),
        ],
        tags=["docs", "share", "permissions", "access", "email", "collaborate"],
        fn=share_document,
    )

    registry.register(
        name="create_header",
        description=(
            "Create a header in a Google Document. "
            "Use DEFAULT for all pages or FIRST for first-page-only."
        ),
        parameters=[
            ToolParameter(
                "document_id",
                "string",
                "The ID of the document (from URL)",
            ),
            ToolParameter(
                "section_type",
                "string",
                "Header type: DEFAULT (all pages) or FIRST (first page only). "
                "Default: DEFAULT",
                required=False,
                default="DEFAULT",
            ),
        ],
        tags=["docs", "header", "create", "page", "top"],
        fn=create_header,
    )

    registry.register(
        name="create_footer",
        description=(
            "Create a footer in a Google Document. "
            "Use DEFAULT for all pages or FIRST for first-page-only."
        ),
        parameters=[
            ToolParameter(
                "document_id",
                "string",
                "The ID of the document (from URL)",
            ),
            ToolParameter(
                "section_type",
                "string",
                "Footer type: DEFAULT (all pages) or FIRST (first page only). "
                "Default: DEFAULT",
                required=False,
                default="DEFAULT",
            ),
        ],
        tags=["docs", "footer", "create", "page", "bottom"],
        fn=create_footer,
    )

    registry.register(
        name="delete_header",
        description="Delete a header from a Google Document by header ID.",
        parameters=[
            ToolParameter(
                "document_id",
                "string",
                "The ID of the document (from URL)",
            ),
            ToolParameter(
                "header_id",
                "string",
                "The header ID (from create_header or get_document)",
            ),
        ],
        tags=["docs", "header", "delete", "remove"],
        fn=delete_header,
    )

    registry.register(
        name="delete_footer",
        description="Delete a footer from a Google Document by footer ID.",
        parameters=[
            ToolParameter(
                "document_id",
                "string",
                "The ID of the document (from URL)",
            ),
            ToolParameter(
                "footer_id",
                "string",
                "The footer ID (from create_footer or get_document)",
            ),
        ],
        tags=["docs", "footer", "delete", "remove"],
        fn=delete_footer,
    )

    registry.register(
        name="create_named_range",
        description=(
            "Create a named range (bookmark) spanning character indices. "
            "Named ranges let tools reference content by name "
            "instead of fragile offsets."
        ),
        parameters=[
            ToolParameter(
                "document_id",
                "string",
                "The ID of the document (from URL)",
            ),
            ToolParameter(
                "name",
                "string",
                "Name for the range (e.g. 'introduction', 'summary')",
            ),
            ToolParameter(
                "start_index",
                "integer",
                "Start character index",
            ),
            ToolParameter(
                "end_index",
                "integer",
                "End character index (exclusive)",
            ),
        ],
        tags=["docs", "named", "range", "bookmark", "create", "anchor"],
        fn=create_named_range,
    )

    registry.register(
        name="delete_named_range",
        description=(
            "Delete a named range by its ID or by name. "
            "If name is provided, all ranges with that name are deleted."
        ),
        parameters=[
            ToolParameter(
                "document_id",
                "string",
                "The ID of the document (from URL)",
            ),
            ToolParameter(
                "named_range_id",
                "string",
                "The named range ID (from create_named_range)",
                required=False,
            ),
            ToolParameter(
                "name",
                "string",
                "Delete all ranges with this name",
                required=False,
            ),
        ],
        tags=["docs", "named", "range", "bookmark", "delete", "remove"],
        fn=delete_named_range,
    )

    registry.register(
        name="replace_named_range_content",
        description=(
            "Replace the content of a named range with new text. "
            "Provide either named_range_id or name to identify the target."
        ),
        parameters=[
            ToolParameter(
                "document_id",
                "string",
                "The ID of the document (from URL)",
            ),
            ToolParameter(
                "text",
                "string",
                "The new text content to insert into the named range",
            ),
            ToolParameter(
                "named_range_id",
                "string",
                "The named range ID (from create_named_range)",
                required=False,
            ),
            ToolParameter(
                "name",
                "string",
                "Replace all ranges with this name",
                required=False,
            ),
        ],
        tags=["docs", "named", "range", "replace", "content", "update"],
        fn=replace_named_range_content,
    )
