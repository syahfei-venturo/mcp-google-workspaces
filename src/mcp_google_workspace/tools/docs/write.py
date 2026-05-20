"""Write operations for Google Docs."""

import re
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import Context

from ...registry import ToolParameter, ToolRegistry
from ._utils import safe_batch_update, validate_document_id
from .read import (
    _extract_paragraph_text,
    _extract_text_with_positions,
    _text_range_to_doc_range,
)


def insert_text(
    document_id: str,
    text: str,
    index: Optional[int] = None,
    segment_id: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Insert text at a specific position in a Google Document.

    For body text, index 1 is the beginning of the document body (default).
    For headers/footers, pass the segment ID via ``segment_id`` — the default
    index is automatically set to 0 (start of the segment) so that inserting
    into a freshly created, empty header or footer works without manually
    specifying the index.

    Use ``segment_id`` to insert into a header or footer
    (pass the header/footer ID from ``create_header``/``create_footer``).
    """
    if err := validate_document_id(document_id):
        return err

    # Auto-select the correct default index:
    # - Segments (header/footer) start at 0 in their own coordinate space.
    # - The document body starts at 1.
    resolved_index = index if index is not None else (0 if segment_id else 1)

    docs_service = ctx.request_context.lifespan_context.docs_service

    location: Dict[str, Any] = {"index": resolved_index}
    if segment_id:
        location["segmentId"] = segment_id

    requests = [
        {
            "insertText": {
                "location": location,
                "text": text,
            }
        }
    ]

    result = safe_batch_update(docs_service, document_id, requests)
    if "error" in result:
        return result

    return {
        "documentId": document_id,
        "insertedAt": resolved_index,
        "segmentId": segment_id,
        "textLength": len(text),
        "replies": result.get("replies", []),
    }


def delete_content(
    document_id: str,
    start_index: int,
    end_index: int,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Delete content within a specified index range in a Google Document."""
    if err := validate_document_id(document_id):
        return err

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


def replace_text(
    document_id: str,
    find_text: str,
    replacement: str,
    match_case: bool = False,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Find and replace all occurrences of text in a Google Document."""
    if err := validate_document_id(document_id):
        return err
    if not find_text:
        return {"error": "find_text must be a non-empty string"}

    docs_service = ctx.request_context.lifespan_context.docs_service

    requests = [
        {
            "replaceAllText": {
                "containsText": {
                    "text": find_text,
                    "matchCase": match_case,
                },
                "replaceText": replacement,
            }
        }
    ]

    result = safe_batch_update(docs_service, document_id, requests)
    if "error" in result:
        return result

    occurrences = 0
    for reply in result.get("replies", []):
        replace_reply = reply.get("replaceAllText", {})
        occurrences = replace_reply.get("occurrencesChanged", 0)

    return {
        "documentId": document_id,
        "findText": find_text,
        "replacement": replacement,
        "occurrencesChanged": occurrences,
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


def _find_occurrences(
    full_text: str,
    find_text: str,
    match_case: bool,
) -> List[re.Match]:
    """Find all occurrences of find_text in full_text, returning Match objects."""
    flags = re.UNICODE | (0 if match_case else re.IGNORECASE)
    pattern = re.compile(re.escape(find_text), flags)
    return list(pattern.finditer(full_text))



def replace_first_text(
    document_id: str,
    find_text: str,
    replacement: str,
    match_case: bool = False,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Replace only the first occurrence of text in a Google Document.

    Unlike ``replace_text`` which replaces *all* occurrences via the
    ``replaceAllText`` API, this function reads the document, locates
    the first match, and performs an atomic delete+insert via
    ``batchUpdate``.

    .. warning:: Not safe for concurrent edits — another user may change
       the document between the read and the write.
    """
    if err := validate_document_id(document_id):
        return err
    if not find_text:
        return {"error": "find_text must not be empty"}
    if not find_text.strip():
        return {"error": "find_text must contain non-whitespace characters"}

    docs_service = ctx.request_context.lifespan_context.docs_service

    doc = docs_service.documents().get(documentId=document_id).execute()
    body = doc.get("body", {})
    content = body.get("content", [])
    full_text, segments = _extract_text_with_positions(content)

    matches = _find_occurrences(full_text, find_text, match_case)

    if not matches:
        return {
            "documentId": document_id,
            "title": doc.get("title"),
            "findText": find_text,
            "occurrencesFound": 0,
        }

    first = matches[0]
    doc_start, doc_end = _text_range_to_doc_range(
        segments, first.start(), first.end()
    )
    if doc_start is None or doc_end is None:
        return {
            "error": (
                "Cannot map match position to document indices. "
                "The match may span across structural boundaries."
            )
        }

    requests: List[Dict[str, Any]] = [
        {
            "deleteContentRange": {
                "range": {"startIndex": doc_start, "endIndex": doc_end}
            }
        }
    ]
    if replacement:
        requests.append(
            {"insertText": {"location": {"index": doc_start}, "text": replacement}}
        )

    result = safe_batch_update(docs_service, document_id, requests)
    if "error" in result:
        return result

    return {
        "documentId": document_id,
        "title": doc.get("title"),
        "findText": find_text,
        "replacement": replacement,
        "replacedAt": doc_start,
        "occurrencesFound": len(matches),
    }


def replace_text_in_range(
    document_id: str,
    find_text: str,
    replacement: str,
    start_index: int,
    end_index: int,
    match_case: bool = False,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Replace all occurrences of text within a specific index range.

    Only matches whose *entire* span falls within ``[start_index, end_index)``
    are replaced.  Matches partially overlapping the range boundary are
    excluded.

    All replacements are applied in a single atomic ``batchUpdate`` call,
    processed in reverse order to preserve earlier indices.

    .. warning:: Not safe for concurrent edits.
    """
    if err := validate_document_id(document_id):
        return err
    if not find_text:
        return {"error": "find_text must not be empty"}
    if not find_text.strip():
        return {"error": "find_text must contain non-whitespace characters"}
    if start_index < 0:
        return {"error": "start_index must be >= 0"}
    if start_index >= end_index:
        return {"error": "start_index must be less than end_index"}

    docs_service = ctx.request_context.lifespan_context.docs_service

    doc = docs_service.documents().get(documentId=document_id).execute()
    body = doc.get("body", {})
    content = body.get("content", [])
    full_text, segments = _extract_text_with_positions(content)

    all_matches = _find_occurrences(full_text, find_text, match_case)

    # Map each match to actual document indices, then filter by range
    mapped: List[tuple] = []  # (doc_start, doc_end, match)
    for m in all_matches:
        ds, de = _text_range_to_doc_range(segments, m.start(), m.end())
        if ds is not None and de is not None:
            mapped.append((ds, de, m))

    in_range = [
        (ds, de, m)
        for ds, de, m in mapped
        if ds >= start_index and de <= end_index
    ]

    if not in_range:
        return {
            "documentId": document_id,
            "title": doc.get("title"),
            "findText": find_text,
            "range": {"startIndex": start_index, "endIndex": end_index},
            "occurrencesReplaced": 0,
        }

    # Build requests in reverse document order to preserve earlier indices
    requests: List[Dict[str, Any]] = []
    for ds, de, _m in sorted(in_range, key=lambda t: t[0], reverse=True):
        requests.append(
            {"deleteContentRange": {"range": {"startIndex": ds, "endIndex": de}}}
        )
        if replacement:
            requests.append(
                {"insertText": {"location": {"index": ds}, "text": replacement}}
            )

    result = safe_batch_update(docs_service, document_id, requests)
    if "error" in result:
        return result

    return {
        "documentId": document_id,
        "title": doc.get("title"),
        "findText": find_text,
        "replacement": replacement,
        "range": {"startIndex": start_index, "endIndex": end_index},
        "occurrencesReplaced": len(in_range),
    }


_HEADING_LEVELS = {
    "HEADING_1": 1,
    "HEADING_2": 2,
    "HEADING_3": 3,
    "HEADING_4": 4,
    "HEADING_5": 5,
    "HEADING_6": 6,
}


def _get_heading_level(element: Dict[str, Any]) -> Optional[int]:
    """Return the heading level (1-6) of an element, or None if not a heading."""
    if "paragraph" not in element:
        return None
    style = (
        element["paragraph"]
        .get("paragraphStyle", {})
        .get("namedStyleType", "NORMAL_TEXT")
    )
    return _HEADING_LEVELS.get(style)


def replace_section_content(
    document_id: str,
    heading_text: str,
    replacement: str,
    match_case: bool = False,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Replace the body content of a section identified by its heading text.

    Finds the first heading whose text matches ``heading_text`` (stripped of
    whitespace for comparison).  The "section body" spans from the end of
    that heading to the start of the next heading at the same or higher
    level, or the end of the document.

    The heading itself is preserved — only the body content is replaced.

    .. warning:: Not safe for concurrent edits.
    """
    if err := validate_document_id(document_id):
        return err
    if not heading_text:
        return {"error": "heading_text must not be empty"}
    if not heading_text.strip():
        return {"error": "heading_text must contain non-whitespace characters"}

    docs_service = ctx.request_context.lifespan_context.docs_service

    doc = docs_service.documents().get(documentId=document_id).execute()
    body = doc.get("body", {})
    content = body.get("content", [])

    # --- Locate the target heading ---
    target = heading_text.strip()
    target_cmp = target if match_case else target.lower()

    heading_idx: Optional[int] = None
    heading_level: Optional[int] = None

    for i, element in enumerate(content):
        level = _get_heading_level(element)
        if level is None:
            continue
        elem_text = _extract_paragraph_text(element["paragraph"]).strip()
        elem_cmp = elem_text if match_case else elem_text.lower()
        if elem_cmp == target_cmp:
            heading_idx = i
            heading_level = level
            break

    if heading_idx is None:
        return {
            "documentId": document_id,
            "title": doc.get("title"),
            "headingText": heading_text.strip(),
            "found": False,
        }

    # --- Determine section body boundaries ---
    heading_element = content[heading_idx]
    body_start = heading_element.get("endIndex", 0)

    # Scan forward for the next heading at same or higher level
    body_end = body_start  # default: empty section
    found_boundary = False

    for element in content[heading_idx + 1 :]:
        level = _get_heading_level(element)
        if level is not None and level <= heading_level:
            # Same or higher level heading — section ends here
            body_end = element.get("startIndex", body_start)
            found_boundary = True
            break

    if not found_boundary:
        # Section extends to end of document
        if heading_idx + 1 < len(content):
            body_end = content[-1].get("endIndex", body_start)
        # else: heading is the only/last element — body_end stays at body_start

    # --- Build and execute requests ---
    section_range = {"startIndex": body_start, "endIndex": body_end}

    requests: List[Dict[str, Any]] = []

    if body_start < body_end:
        requests.append(
            {
                "deleteContentRange": {
                    "range": {
                        "startIndex": body_start,
                        "endIndex": body_end,
                    }
                }
            }
        )

    if replacement:
        requests.append(
            {
                "insertText": {
                    "location": {"index": body_start},
                    "text": replacement,
                }
            }
        )

    if requests:
        result = safe_batch_update(docs_service, document_id, requests)
        if "error" in result:
            return result

    return {
        "documentId": document_id,
        "title": doc.get("title"),
        "headingText": heading_text.strip(),
        "found": True,
        "sectionRange": section_range,
        "replacement": replacement,
    }


def register(registry: ToolRegistry) -> None:
    """Register all Docs write tools in the registry."""
    registry.register(
        name="insert_text",
        description=(
            "Insert text at a specific position in a Google Document. "
            "Index 1 is the beginning of the document body. "
            "Use segment_id to insert into a header or footer "
            "(pass the header/footer ID from create_header/create_footer). "
            "When segment_id is provided the default index is 0 (start of segment), "
            "so you can omit index entirely when inserting into a fresh header/footer."
        ),
        parameters=[
            ToolParameter(
                "document_id",
                "string",
                "The ID of the document (from URL)",
            ),
            ToolParameter("text", "string", "The text to insert"),
            ToolParameter(
                "index",
                "integer",
                "Character index to insert at. "
                "Defaults to 1 (start of body) for body text, "
                "or 0 (start of segment) when segment_id is provided. "
                "Omit to use the smart default.",
                required=False,
            ),
            ToolParameter(
                "segment_id",
                "string",
                "Segment ID for inserting into a header or footer. "
                "Use the ID returned by create_header or create_footer. "
                "Omit to insert into the document body.",
                required=False,
            ),
        ],
        tags=["docs", "write", "insert", "text", "content", "add", "header", "footer"],
        fn=insert_text,
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
        name="replace_text",
        description=("Find and replace all occurrences of text in a Google Document."),
        parameters=[
            ToolParameter(
                "document_id",
                "string",
                "The ID of the document (from URL)",
            ),
            ToolParameter("find_text", "string", "Text to find"),
            ToolParameter("replacement", "string", "Replacement text"),
            ToolParameter(
                "match_case",
                "boolean",
                "Case-sensitive matching (default: false)",
                required=False,
                default=False,
            ),
        ],
        tags=["docs", "write", "replace", "find", "text", "substitution"],
        fn=replace_text,
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
        name="replace_first_text",
        description=(
            "Replace only the first occurrence of text in a Google Document. "
            "Useful when a document contains duplicate text and you need to "
            "target just the first one. Uses atomic delete+insert."
        ),
        parameters=[
            ToolParameter(
                "document_id",
                "string",
                "The ID of the document (from URL)",
            ),
            ToolParameter("find_text", "string", "Text to find"),
            ToolParameter("replacement", "string", "Replacement text"),
            ToolParameter(
                "match_case",
                "boolean",
                "Case-sensitive matching (default: false)",
                required=False,
                default=False,
            ),
        ],
        tags=[
            "docs", "write", "replace", "find", "text",
            "first", "single", "occurrence",
        ],
        fn=replace_first_text,
    )

    registry.register(
        name="replace_text_in_range",
        description=(
            "Replace all occurrences of text within a specific index range "
            "in a Google Document. Only matches fully inside the range are "
            "replaced. Use get_document or search_document to find indices. "
            "Uses atomic delete+insert."
        ),
        parameters=[
            ToolParameter(
                "document_id",
                "string",
                "The ID of the document (from URL)",
            ),
            ToolParameter("find_text", "string", "Text to find"),
            ToolParameter("replacement", "string", "Replacement text"),
            ToolParameter(
                "start_index",
                "integer",
                "Start of the index range (inclusive)",
            ),
            ToolParameter(
                "end_index",
                "integer",
                "End of the index range (exclusive)",
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
            "docs", "write", "replace", "find", "text",
            "range", "index", "bounded", "scoped",
        ],
        fn=replace_text_in_range,
    )

    registry.register(
        name="replace_section_content",
        description=(
            "Replace the body content of a section identified by its heading "
            "text. Finds the first heading matching the given text and replaces "
            "everything between it and the next same-or-higher level heading "
            "(or end of document). The heading itself is preserved. "
            "Ideal for rewriting specific sections without calculating indices."
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
                "The heading text to find (matched after stripping whitespace)",
            ),
            ToolParameter(
                "replacement",
                "string",
                "New content to replace the section body with",
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
            "content", "anchor", "structured",
        ],
        fn=replace_section_content,
    )
