"""Write operations for Google Docs (HTML-based).

All write tools use the Drive API export→modify→upload pattern:
1. Export document as HTML via Drive API
2. Modify the HTML string
3. Re-upload via Drive API media update

This preserves document ID, sharing settings, and comments.
"""

import logging
import re
from typing import Any, Dict, List, Optional

from googleapiclient.errors import HttpError
from googleapiclient.http import MediaInMemoryUpload
from mcp.server.fastmcp import Context

from ...registry import ToolParameter, ToolRegistry
from ...utils.common import sanitize_http_error
from ._utils import validate_document_id

logger = logging.getLogger(__name__)

# Maximum HTML content size (5 MB)
MAX_HTML_BYTES = 5 * 1024 * 1024


def _export_html(drive_service, document_id: str) -> tuple:
    """Export a document as HTML. Returns (html_str, file_meta, error_dict).

    On success error_dict is None. On failure html_str and file_meta are None.
    """
    try:
        file_meta = (
            drive_service.files()
            .get(fileId=document_id, supportsAllDrives=True, fields="id, name")
            .execute()
        )
    except HttpError as e:
        return None, None, {"error": sanitize_http_error(e, "Get document metadata")}
    except Exception as e:
        logger.error("Get document metadata failed: %s", e)
        return None, None, {"error": f"Get document metadata failed: {e}"}

    try:
        html_bytes = (
            drive_service.files()
            .export(fileId=document_id, mimeType="text/html")
            .execute()
        )
        return html_bytes.decode("utf-8"), file_meta, None
    except HttpError as e:
        return None, None, {"error": sanitize_http_error(e, "Export document as HTML")}
    except Exception as e:
        logger.error("Export document as HTML failed: %s", e)
        return None, None, {"error": "Export document as HTML failed: unexpected error"}


def _upload_html(drive_service, document_id: str, html_content: str) -> Optional[Dict[str, Any]]:
    """Re-upload modified HTML to overwrite the document. Returns error dict or None."""
    html_bytes = html_content.encode("utf-8")
    if len(html_bytes) > MAX_HTML_BYTES:
        return {
            "error": (
                f"HTML content exceeds maximum size "
                f"({len(html_bytes):,} bytes > {MAX_HTML_BYTES:,} bytes)"
            )
        }

    media = MediaInMemoryUpload(html_bytes, mimetype="text/html")

    try:
        drive_service.files().update(
            fileId=document_id,
            media_body=media,
            supportsAllDrives=True,
            fields="id",
        ).execute()
        return None
    except HttpError as e:
        return {"error": sanitize_http_error(e, "Update document")}
    except Exception as e:
        logger.error("Update document failed: %s", e)
        return {"error": "Update document failed: unexpected error"}


def _strip_html_tags(html: str) -> str:
    """Strip HTML tags to get plain text (for text-based searching)."""
    return re.sub(r"<[^>]+>", "", html)


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------


def insert_text_with_html(
    document_id: str,
    html_content: str,
    position: str = "end",
    after_text: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Insert HTML content into a Google Document.

    ``position`` controls where the content is inserted:
    - ``"end"``: append to the end of the document (default)
    - ``"beginning"``: insert at the start of the document body
    - ``"after_text"``: insert after the first occurrence of ``after_text``
    """
    if err := validate_document_id(document_id):
        return err
    if not html_content or not html_content.strip():
        return {"error": "html_content must be a non-empty string"}
    if position not in ("beginning", "end", "after_text"):
        return {"error": "position must be 'beginning', 'end', or 'after_text'"}
    if position == "after_text" and (not after_text or not after_text.strip()):
        return {"error": "after_text must be provided when position is 'after_text'"}

    drive_service = ctx.request_context.lifespan_context.drive_service

    current_html, file_meta, err = _export_html(drive_service, document_id)
    if err:
        return err

    if position == "end":
        # Insert before </body>
        match = re.search(r"</body>", current_html, re.IGNORECASE)
        if match:
            insert_pos = match.start()
            combined = current_html[:insert_pos] + html_content + current_html[insert_pos:]
        else:
            combined = current_html + html_content
    elif position == "beginning":
        # Insert after <body...>
        match = re.search(r"<body[^>]*>", current_html, re.IGNORECASE)
        if match:
            insert_pos = match.end()
            combined = current_html[:insert_pos] + html_content + current_html[insert_pos:]
        else:
            combined = html_content + current_html
    else:
        # after_text: find the text in HTML and insert after it
        # Search for after_text in the HTML content (as literal text within tags)
        escaped = re.escape(after_text)
        match = re.search(escaped, current_html)
        if not match:
            return {
                "documentId": document_id,
                "title": file_meta.get("name", ""),
                "error": f"Text '{after_text}' not found in document HTML",
            }
        # Find the end of the enclosing tag after the match
        insert_pos = match.end()
        # Try to find the closing tag boundary
        close_tag = re.search(r"</[^>]+>", current_html[insert_pos:])
        if close_tag:
            insert_pos += close_tag.end()
        combined = current_html[:insert_pos] + html_content + current_html[insert_pos:]

    upload_err = _upload_html(drive_service, document_id, combined)
    if upload_err:
        return upload_err

    return {
        "documentId": document_id,
        "title": file_meta.get("name", ""),
        "position": position,
        "insertedLength": len(html_content),
        "status": "inserted",
    }


def delete_content(
    document_id: str,
    start_index: int,
    end_index: int,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Delete content within a specified index range in a Google Document.

    Uses the Docs API batchUpdate for precise index-based deletion.
    """
    if err := validate_document_id(document_id):
        return err

    from ._utils import safe_batch_update

    docs_service = ctx.request_context.lifespan_context.docs_service

    if start_index >= end_index:
        return {"error": "start_index must be less than end_index"}

    requests = [
        {
            "deleteContentRange": {
                "range": {
                    "startIndex": start_index,
                    "endIndex": end_index,
                }
            }
        }
    ]

    result = safe_batch_update(docs_service, document_id, requests)
    if "error" in result:
        return result

    return {
        "documentId": document_id,
        "deletedRange": {"startIndex": start_index, "endIndex": end_index},
        "replies": result.get("replies", []),
    }


def replace_text_with_html(
    document_id: str,
    find_text: str,
    replacement_html: str,
    match_case: bool = False,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Find text and replace all occurrences with HTML content.

    Exports the document as HTML, performs find-and-replace on the
    HTML content, and re-uploads. The ``find_text`` is searched as
    literal text within the HTML. The ``replacement_html`` can contain
    any valid HTML tags for rich formatting.
    """
    if err := validate_document_id(document_id):
        return err
    if not find_text:
        return {"error": "find_text must be a non-empty string"}

    drive_service = ctx.request_context.lifespan_context.drive_service

    current_html, file_meta, err = _export_html(drive_service, document_id)
    if err:
        return err

    flags = 0 if match_case else re.IGNORECASE
    pattern = re.compile(re.escape(find_text), flags)
    occurrences = len(pattern.findall(current_html))

    if occurrences == 0:
        return {
            "documentId": document_id,
            "title": file_meta.get("name", ""),
            "findText": find_text,
            "occurrencesChanged": 0,
        }

    combined = pattern.sub(replacement_html, current_html)

    upload_err = _upload_html(drive_service, document_id, combined)
    if upload_err:
        return upload_err

    return {
        "documentId": document_id,
        "title": file_meta.get("name", ""),
        "findText": find_text,
        "occurrencesChanged": occurrences,
        "status": "replaced",
    }


def update_formatting(
    document_id: str,
    start_index: int,
    end_index: int,
    bold: Optional[bool] = None,
    italic: Optional[bool] = None,
    underline: Optional[bool] = None,
    font_size: Optional[int] = None,
    font_family: Optional[str] = None,
    foreground_color: Optional[Dict[str, float]] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Update text formatting within a specified range in a Google Document.

    At least one formatting option must be provided.
    foreground_color should be a dict with 'red', 'green', 'blue' keys (0.0-1.0).
    """
    if err := validate_document_id(document_id):
        return err

    if start_index >= end_index:
        return {"error": "start_index must be less than end_index"}

    from ._utils import safe_batch_update

    docs_service = ctx.request_context.lifespan_context.docs_service

    text_style: Dict[str, Any] = {}
    fields: List[str] = []

    if bold is not None:
        text_style["bold"] = bold
        fields.append("bold")
    if italic is not None:
        text_style["italic"] = italic
        fields.append("italic")
    if underline is not None:
        text_style["underline"] = underline
        fields.append("underline")
    if font_size is not None:
        text_style["fontSize"] = {"magnitude": font_size, "unit": "PT"}
        fields.append("fontSize")
    if font_family is not None:
        text_style["weightedFontFamily"] = {"fontFamily": font_family}
        fields.append("weightedFontFamily")
    if foreground_color is not None:
        text_style["foregroundColor"] = {"color": {"rgbColor": foreground_color}}
        fields.append("foregroundColor")

    if not fields:
        return {"error": "At least one formatting option must be provided"}

    requests = [
        {
            "updateTextStyle": {
                "range": {
                    "startIndex": start_index,
                    "endIndex": end_index,
                },
                "textStyle": text_style,
                "fields": ",".join(fields),
            }
        }
    ]

    result = safe_batch_update(docs_service, document_id, requests)
    if "error" in result:
        return result

    return {
        "documentId": document_id,
        "formattedRange": {"startIndex": start_index, "endIndex": end_index},
        "appliedStyles": fields,
        "replies": result.get("replies", []),
    }


def replace_first_text_with_html(
    document_id: str,
    find_text: str,
    replacement_html: str,
    match_case: bool = False,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Replace only the first occurrence of text with HTML content.

    Exports the document as HTML, finds the first match, replaces it
    with ``replacement_html``, and re-uploads.
    """
    if err := validate_document_id(document_id):
        return err
    if not find_text:
        return {"error": "find_text must not be empty"}
    if not find_text.strip():
        return {"error": "find_text must contain non-whitespace characters"}

    drive_service = ctx.request_context.lifespan_context.drive_service

    current_html, file_meta, err = _export_html(drive_service, document_id)
    if err:
        return err

    flags = 0 if match_case else re.IGNORECASE
    pattern = re.compile(re.escape(find_text), flags)

    match = pattern.search(current_html)
    if not match:
        return {
            "documentId": document_id,
            "title": file_meta.get("name", ""),
            "findText": find_text,
            "occurrencesFound": 0,
        }

    total_matches = len(pattern.findall(current_html))

    # Replace only the first occurrence
    combined = current_html[:match.start()] + replacement_html + current_html[match.end():]

    upload_err = _upload_html(drive_service, document_id, combined)
    if upload_err:
        return upload_err

    return {
        "documentId": document_id,
        "title": file_meta.get("name", ""),
        "findText": find_text,
        "occurrencesFound": total_matches,
        "status": "replaced_first",
    }


def replace_text_in_range_with_html(
    document_id: str,
    find_text: str,
    replacement_html: str,
    range_start_text: str,
    range_end_text: str,
    match_case: bool = False,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Replace all occurrences of text within a text-bounded range with HTML.

    Instead of numeric indices, this tool uses ``range_start_text`` and
    ``range_end_text`` to define the search boundary within the HTML.
    Only matches within the bounded region are replaced.
    """
    if err := validate_document_id(document_id):
        return err
    if not find_text:
        return {"error": "find_text must not be empty"}
    if not find_text.strip():
        return {"error": "find_text must contain non-whitespace characters"}
    if not range_start_text or not range_start_text.strip():
        return {"error": "range_start_text must be a non-empty string"}
    if not range_end_text or not range_end_text.strip():
        return {"error": "range_end_text must be a non-empty string"}

    drive_service = ctx.request_context.lifespan_context.drive_service

    current_html, file_meta, err = _export_html(drive_service, document_id)
    if err:
        return err

    flags = 0 if match_case else re.IGNORECASE

    # Find the range boundaries in HTML
    start_match = re.search(re.escape(range_start_text), current_html, flags)
    if not start_match:
        return {
            "documentId": document_id,
            "title": file_meta.get("name", ""),
            "error": f"range_start_text '{range_start_text}' not found",
        }

    end_match = re.search(re.escape(range_end_text), current_html[start_match.start():], flags)
    if not end_match:
        return {
            "documentId": document_id,
            "title": file_meta.get("name", ""),
            "error": f"range_end_text '{range_end_text}' not found after range_start_text",
        }

    abs_range_start = start_match.start()
    abs_range_end = start_match.start() + end_match.end()

    # Extract the range section
    range_section = current_html[abs_range_start:abs_range_end]

    # Replace within the range
    pattern = re.compile(re.escape(find_text), flags)
    occurrences = len(pattern.findall(range_section))
    modified_section = pattern.sub(replacement_html, range_section)

    if occurrences == 0:
        return {
            "documentId": document_id,
            "title": file_meta.get("name", ""),
            "findText": find_text,
            "occurrencesReplaced": 0,
        }

    combined = current_html[:abs_range_start] + modified_section + current_html[abs_range_end:]

    upload_err = _upload_html(drive_service, document_id, combined)
    if upload_err:
        return upload_err

    return {
        "documentId": document_id,
        "title": file_meta.get("name", ""),
        "findText": find_text,
        "occurrencesReplaced": occurrences,
        "status": "replaced",
    }


def replace_section_content_with_html(
    document_id: str,
    heading_text: str,
    replacement_html: str,
    match_case: bool = False,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Replace the body content of a section identified by its heading with HTML.

    Exports the document as HTML, finds the heading element matching
    ``heading_text``, and replaces all content between it and the next
    same-or-higher level heading (or end of body) with ``replacement_html``.
    The heading itself is preserved.
    """
    if err := validate_document_id(document_id):
        return err
    if not heading_text:
        return {"error": "heading_text must not be empty"}
    if not heading_text.strip():
        return {"error": "heading_text must contain non-whitespace characters"}

    drive_service = ctx.request_context.lifespan_context.drive_service

    current_html, file_meta, err = _export_html(drive_service, document_id)
    if err:
        return err

    flags = 0 if match_case else re.IGNORECASE
    target = heading_text.strip()

    # Find the heading element in HTML (h1-h6)
    heading_pattern = re.compile(
        r"(<h([1-6])[^>]*>.*?" + re.escape(target) + r".*?</h\2>)",
        flags | re.DOTALL,
    )
    heading_match = heading_pattern.search(current_html)

    if not heading_match:
        return {
            "documentId": document_id,
            "title": file_meta.get("name", ""),
            "headingText": target,
            "found": False,
        }

    heading_level = int(heading_match.group(2))
    section_start = heading_match.end()

    # Find the next heading at same or higher level
    next_heading_pattern = re.compile(
        r"<h([1-" + str(heading_level) + r"])[^>]*>",
        re.IGNORECASE,
    )
    next_match = next_heading_pattern.search(current_html[section_start:])

    if next_match:
        section_end = section_start + next_match.start()
    else:
        # Section extends to </body> or end of document
        body_end = re.search(r"</body>", current_html[section_start:], re.IGNORECASE)
        if body_end:
            section_end = section_start + body_end.start()
        else:
            section_end = len(current_html)

    combined = (
        current_html[:section_start]
        + replacement_html
        + current_html[section_end:]
    )

    upload_err = _upload_html(drive_service, document_id, combined)
    if upload_err:
        return upload_err

    return {
        "documentId": document_id,
        "title": file_meta.get("name", ""),
        "headingText": target,
        "found": True,
        "status": "replaced",
    }


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register(registry: ToolRegistry) -> None:
    """Register all Docs write tools in the registry."""
    registry.register(
        name="insert_text_with_html",
        description=(
            "Insert HTML content into a Google Document at a specified position. "
            "Supports 'beginning', 'end' (default), or 'after_text' to insert "
            "after a specific text occurrence. Supports rich HTML formatting."
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
                "HTML content to insert. Supports standard HTML tags: "
                "h1-h6, p, table, ul, ol, li, b, i, a, img, br, hr, etc.",
            ),
            ToolParameter(
                "position",
                "string",
                "Where to insert: 'beginning', 'end' (default), or 'after_text'.",
                required=False,
                default="end",
            ),
            ToolParameter(
                "after_text",
                "string",
                "Text to insert after (required when position='after_text').",
                required=False,
            ),
        ],
        tags=["docs", "write", "insert", "html", "content", "add", "rich", "format"],
        fn=insert_text_with_html,
    )

    registry.register(
        name="delete_content",
        description=(
            "Delete content within a specified index range in a Google Document."
        ),
        parameters=[
            ToolParameter(
                "document_id",
                "string",
                "The ID of the document (from URL)",
            ),
            ToolParameter(
                "start_index",
                "integer",
                "Start character index of content to delete",
            ),
            ToolParameter(
                "end_index",
                "integer",
                "End character index of content to delete (exclusive)",
            ),
        ],
        tags=["docs", "write", "delete", "content", "remove", "range"],
        fn=delete_content,
    )

    registry.register(
        name="replace_text_with_html",
        description=(
            "Find and replace all occurrences of text with HTML content "
            "in a Google Document. The find_text is searched as literal text. "
            "The replacement can contain rich HTML formatting."
        ),
        parameters=[
            ToolParameter(
                "document_id",
                "string",
                "The ID of the document (from URL)",
            ),
            ToolParameter("find_text", "string", "Text to find"),
            ToolParameter(
                "replacement_html",
                "string",
                "HTML content to replace with. Supports standard HTML tags.",
            ),
            ToolParameter(
                "match_case",
                "boolean",
                "Case-sensitive matching (default: false)",
                required=False,
                default=False,
            ),
        ],
        tags=["docs", "write", "replace", "find", "html", "substitution", "rich"],
        fn=replace_text_with_html,
    )

    registry.register(
        name="update_formatting",
        description=(
            "Update text formatting (bold, italic, underline, font size, "
            "font family, color) within a specified range in a Google Document."
        ),
        parameters=[
            ToolParameter(
                "document_id",
                "string",
                "The ID of the document (from URL)",
            ),
            ToolParameter(
                "start_index",
                "integer",
                "Start character index of text to format",
            ),
            ToolParameter(
                "end_index",
                "integer",
                "End character index of text to format (exclusive)",
            ),
            ToolParameter(
                "bold",
                "boolean",
                "Set bold formatting",
                required=False,
            ),
            ToolParameter(
                "italic",
                "boolean",
                "Set italic formatting",
                required=False,
            ),
            ToolParameter(
                "underline",
                "boolean",
                "Set underline formatting",
                required=False,
            ),
            ToolParameter(
                "font_size",
                "integer",
                "Font size in points",
                required=False,
            ),
            ToolParameter(
                "font_family",
                "string",
                "Font family name (e.g., 'Arial', 'Times New Roman')",
                required=False,
            ),
            ToolParameter(
                "foreground_color",
                "object",
                "Text color as {red, green, blue} with values 0.0-1.0",
                required=False,
            ),
        ],
        tags=["docs", "write", "format", "style", "bold", "italic", "font"],
        fn=update_formatting,
    )

    registry.register(
        name="replace_first_text_with_html",
        description=(
            "Replace only the first occurrence of text with HTML content "
            "in a Google Document. Useful when a document contains duplicate "
            "text and you need to target just the first one."
        ),
        parameters=[
            ToolParameter(
                "document_id",
                "string",
                "The ID of the document (from URL)",
            ),
            ToolParameter("find_text", "string", "Text to find"),
            ToolParameter(
                "replacement_html",
                "string",
                "HTML content to replace with. Supports standard HTML tags.",
            ),
            ToolParameter(
                "match_case",
                "boolean",
                "Case-sensitive matching (default: false)",
                required=False,
                default=False,
            ),
        ],
        tags=[
            "docs", "write", "replace", "find", "html",
            "first", "single", "occurrence", "rich",
        ],
        fn=replace_first_text_with_html,
    )

    registry.register(
        name="replace_text_in_range_with_html",
        description=(
            "Replace all occurrences of text within a text-bounded range "
            "with HTML content. Uses range_start_text and range_end_text "
            "to define the search boundary instead of numeric indices. "
            "Only matches within the bounded region are replaced."
        ),
        parameters=[
            ToolParameter(
                "document_id",
                "string",
                "The ID of the document (from URL)",
            ),
            ToolParameter("find_text", "string", "Text to find"),
            ToolParameter(
                "replacement_html",
                "string",
                "HTML content to replace with. Supports standard HTML tags.",
            ),
            ToolParameter(
                "range_start_text",
                "string",
                "Text marking the start of the search range",
            ),
            ToolParameter(
                "range_end_text",
                "string",
                "Text marking the end of the search range",
            ),
            ToolParameter(
                "match_case",
                "boolean",
                "Case-sensitive matching (default: false)",
                required=False,
                default=False,
            ),
        ],
        tags=[
            "docs", "write", "replace", "find", "html",
            "range", "bounded", "scoped", "rich",
        ],
        fn=replace_text_in_range_with_html,
    )

    registry.register(
        name="replace_section_content_with_html",
        description=(
            "Replace the body content of a section identified by its heading "
            "text with HTML content. Finds the first heading matching the given "
            "text and replaces everything between it and the next same-or-higher "
            "level heading (or end of document). The heading itself is preserved."
        ),
        parameters=[
            ToolParameter(
                "document_id",
                "string",
                "The ID of the document (from URL)",
            ),
            ToolParameter(
                "heading_text",
                "string",
                "The heading text to find",
            ),
            ToolParameter(
                "replacement_html",
                "string",
                "HTML content to replace the section body with. "
                "Supports standard HTML tags.",
            ),
            ToolParameter(
                "match_case",
                "boolean",
                "Case-sensitive heading matching (default: false)",
                required=False,
                default=False,
            ),
        ],
        tags=[
            "docs", "write", "replace", "section", "heading",
            "html", "content", "anchor", "structured", "rich",
        ],
        fn=replace_section_content_with_html,
    )
