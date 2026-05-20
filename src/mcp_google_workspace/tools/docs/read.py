"""Read operations for Google Docs."""

import re
from typing import Any, Dict, List, Optional, Tuple

from mcp.server.fastmcp import Context

from ...registry import ToolParameter, ToolRegistry
from ._utils import safe_get_document, validate_document_id

_VALID_MATCH_TYPES = {"contains", "exact", "regex", "starts_with"}
_MAX_QUERY_LENGTH = 1000


def _extract_text_from_elements(elements: List[Dict[str, Any]]) -> str:
    """Recursively extract plain text from document structural elements."""
    text_parts: List[str] = []
    for element in elements:
        if "paragraph" in element:
            for para_element in element["paragraph"].get("elements", []):
                text_run = para_element.get("textRun")
                if text_run:
                    text_parts.append(text_run.get("content", ""))
        elif "table" in element:
            for row in element["table"].get("tableRows", []):
                for cell in row.get("tableCells", []):
                    cell_content = cell.get("content", [])
                    text_parts.append(_extract_text_from_elements(cell_content))
        elif "sectionBreak" in element:
            continue
    return "".join(text_parts)


# ---------------------------------------------------------------------------
# Index-aware text extraction
# ---------------------------------------------------------------------------

# A segment maps a slice of the flattened text to its actual document index.
# (text_offset, doc_start_index, length)
TextSegment = Tuple[int, int, int]


def _extract_text_with_positions(
    elements: List[Dict[str, Any]],
) -> Tuple[str, List[TextSegment]]:
    """Extract text **and** build a text-offset → document-index map.

    Returns ``(flattened_text, segments)`` where each segment is a
    ``(text_offset, doc_start_index, length)`` tuple.  The mapping
    accounts for structural elements (tables, rows, cells) that consume
    document indices without producing text.
    """
    text_parts: List[str] = []
    segments: List[TextSegment] = []
    text_offset = 0

    for element in elements:
        if "paragraph" in element:
            elem_start = element.get("startIndex", 0)
            local_offset = 0
            for para_elem in element["paragraph"].get("elements", []):
                text_run = para_elem.get("textRun")
                if text_run:
                    content = text_run.get("content", "")
                    if content:
                        doc_idx = para_elem.get(
                            "startIndex", elem_start + local_offset
                        )
                        segments.append((text_offset, doc_idx, len(content)))
                        text_parts.append(content)
                        text_offset += len(content)
                        local_offset += len(content)
                else:
                    # Non-text elements (inlineObject, etc.) consume index
                    # space but produce no text.
                    el_len = para_elem.get("endIndex", 0) - para_elem.get(
                        "startIndex", 0
                    )
                    local_offset += max(el_len, 0)
        elif "table" in element:
            for row in element["table"].get("tableRows", []):
                for cell in row.get("tableCells", []):
                    sub_text, sub_segs = _extract_text_with_positions(
                        cell.get("content", [])
                    )
                    for sub_off, sub_doc, sub_len in sub_segs:
                        segments.append(
                            (text_offset + sub_off, sub_doc, sub_len)
                        )
                    text_parts.append(sub_text)
                    text_offset += len(sub_text)

    return "".join(text_parts), segments


def _text_pos_to_doc_index(
    segments: List[TextSegment], text_pos: int
) -> Optional[int]:
    """Convert a single flattened-text position to its document index."""
    for text_offset, doc_index, length in segments:
        if text_offset <= text_pos < text_offset + length:
            return doc_index + (text_pos - text_offset)
    return None


def _text_range_to_doc_range(
    segments: List[TextSegment], text_start: int, text_end: int
) -> Tuple[Optional[int], Optional[int]]:
    """Convert a flattened-text range ``[text_start, text_end)`` to document indices.

    Returns ``(doc_start, doc_end)`` or ``(None, None)`` if the range
    cannot be mapped (e.g. spans non-contiguous structural boundaries).
    """
    doc_start: Optional[int] = None
    doc_end: Optional[int] = None

    for text_offset, doc_index, length in segments:
        seg_end = text_offset + length
        if doc_start is None and text_offset <= text_start < seg_end:
            doc_start = doc_index + (text_start - text_offset)
        if text_offset < text_end <= seg_end:
            doc_end = doc_index + (text_end - text_offset)
            break

    return doc_start, doc_end


def get_document(
    document_id: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get the full structure and metadata of a Google Document."""
    if err := validate_document_id(document_id):
        return err

    docs_service = ctx.request_context.lifespan_context.docs_service

    doc = safe_get_document(docs_service, document_id)
    if "error" in doc:
        return doc

    return {
        "documentId": doc.get("documentId"),
        "title": doc.get("title"),
        "revisionId": doc.get("revisionId"),
        "body": doc.get("body"),
        "headers": doc.get("headers"),
        "footers": doc.get("footers"),
        "documentStyle": doc.get("documentStyle"),
    }


def get_text(
    document_id: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Extract plain text content from a Google Document."""
    if err := validate_document_id(document_id):
        return err

    docs_service = ctx.request_context.lifespan_context.docs_service

    doc = safe_get_document(docs_service, document_id)
    if "error" in doc:
        return doc

    body = doc.get("body", {})
    content = body.get("content", [])

    text = _extract_text_from_elements(content)

    return {
        "documentId": doc.get("documentId"),
        "title": doc.get("title"),
        "text": text,
        "length": len(text),
    }


def get_tables(
    document_id: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Extract all tables from a Google Document with their content."""
    if err := validate_document_id(document_id):
        return err

    docs_service = ctx.request_context.lifespan_context.docs_service

    doc = safe_get_document(docs_service, document_id)
    if "error" in doc:
        return doc

    body = doc.get("body", {})
    content = body.get("content", [])

    tables: List[Dict[str, Any]] = []
    for idx, element in enumerate(content):
        if "table" not in element:
            continue

        table = element["table"]
        rows_data: List[List[str]] = []
        cell_indices: List[List[Dict[str, Any]]] = []

        for row in table.get("tableRows", []):
            row_cells: List[str] = []
            row_indices: List[Dict[str, Any]] = []
            for cell in row.get("tableCells", []):
                cell_content = cell.get("content", [])
                cell_text = _extract_text_from_elements(cell_content).strip()
                row_cells.append(cell_text)

                # Extract per-cell content indices from structural elements
                c_start = None
                c_end = None
                if cell_content:
                    c_start = cell_content[0].get("startIndex")
                    c_end = cell_content[-1].get("endIndex")
                row_indices.append({"startIndex": c_start, "endIndex": c_end})

            rows_data.append(row_cells)
            cell_indices.append(row_indices)

        tables.append(
            {
                "tableIndex": idx,
                "rows": table.get("rows", 0),
                "columns": table.get("columns", 0),
                "data": rows_data,
                "startIndex": element.get("startIndex"),
                "endIndex": element.get("endIndex"),
                "cellIndices": cell_indices,
            }
        )

    return {
        "documentId": doc.get("documentId"),
        "title": doc.get("title"),
        "tableCount": len(tables),
        "tables": tables,
    }


_HEADING_STYLE_MAP = {
    "HEADING_1": "heading_1",
    "HEADING_2": "heading_2",
    "HEADING_3": "heading_3",
    "HEADING_4": "heading_4",
    "HEADING_5": "heading_5",
    "HEADING_6": "heading_6",
}


def _classify_element(element: Dict[str, Any]) -> Optional[str]:
    """Return the segment type for a structural element, or None to skip."""
    if "paragraph" in element:
        style = (
            element["paragraph"]
            .get("paragraphStyle", {})
            .get("namedStyleType", "NORMAL_TEXT")
        )
        return _HEADING_STYLE_MAP.get(style, "paragraph")
    if "table" in element:
        return "table"
    # sectionBreak, tableOfContents, etc. — skip
    return None


def _extract_paragraph_text(paragraph: Dict[str, Any]) -> str:
    """Extract concatenated text from a paragraph's elements."""
    parts: List[str] = []
    for elem in paragraph.get("elements", []):
        text_run = elem.get("textRun")
        if text_run:
            parts.append(text_run.get("content", ""))
    return "".join(parts)


def get_text_with_indices(
    document_id: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Return document text annotated with character indices per segment.

    Each structural element (paragraph, heading, table) becomes a segment
    with its text, start/end indices, and type.  This enables LLMs to
    accurately target positions when using index-based editing tools
    like ``replace_text_in_range``.
    """
    if err := validate_document_id(document_id):
        return err

    docs_service = ctx.request_context.lifespan_context.docs_service

    doc = safe_get_document(docs_service, document_id)
    if "error" in doc:
        return doc

    body = doc.get("body", {})
    content = body.get("content", [])

    segments: List[Dict[str, Any]] = []
    total_length = 0

    for element in content:
        seg_type = _classify_element(element)
        if seg_type is None:
            continue

        start_idx = element.get("startIndex", 0)
        end_idx = element.get("endIndex", 0)

        if seg_type == "table":
            table = element["table"]
            text = _extract_text_from_elements([element])
            seg: Dict[str, Any] = {
                "text": text,
                "startIndex": start_idx,
                "endIndex": end_idx,
                "type": seg_type,
                "rows": table.get("rows", 0),
                "columns": table.get("columns", 0),
            }
        else:
            text = _extract_paragraph_text(element["paragraph"])
            seg = {
                "text": text,
                "startIndex": start_idx,
                "endIndex": end_idx,
                "type": seg_type,
            }

        total_length += len(text)
        segments.append(seg)

    return {
        "documentId": doc.get("documentId"),
        "title": doc.get("title"),
        "totalLength": total_length,
        "segments": segments,
    }


def _extract_context(full_text: str, start: int, end: int, radius: int = 50) -> str:
    """Extract context around a match, expanding to word boundaries."""
    ctx_start = max(0, start - radius)
    ctx_end = min(len(full_text), end + radius)

    # Expand to word boundaries (don't cut mid-word)
    if ctx_start > 0:
        space = full_text.rfind(" ", 0, ctx_start)
        ctx_start = space + 1 if space != -1 else 0

    if ctx_end < len(full_text):
        space = full_text.find(" ", ctx_end)
        if space != -1:
            ctx_end = space

    return full_text[ctx_start:ctx_end]


def search_document(
    document_id: str,
    query: str,
    match_type: str = "contains",
    case_sensitive: bool = False,
    max_results: int = 50,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Search for text patterns within a Google Document.

    Parameters
    ----------
    match_type : str
        Matching strategy: ``contains`` (default substring),
        ``exact`` (whole-word boundary), ``starts_with`` (word prefix),
        or ``regex`` (regular expression).
    """
    if err := validate_document_id(document_id):
        return err
    if not query or not query.strip():
        return {"error": "query must be a non-empty string"}
    if len(query) > _MAX_QUERY_LENGTH:
        return {"error": f"query must be <= {_MAX_QUERY_LENGTH} characters"}
    if match_type not in _VALID_MATCH_TYPES:
        return {
            "error": (
                f"Invalid match_type '{match_type}'. "
                f"Must be one of: {', '.join(sorted(_VALID_MATCH_TYPES))}"
            )
        }

    docs_service = ctx.request_context.lifespan_context.docs_service

    doc = safe_get_document(docs_service, document_id)
    if "error" in doc:
        return doc

    body = doc.get("body", {})
    content = body.get("content", [])

    full_text, segments = _extract_text_with_positions(content)

    # Build the appropriate regex pattern
    flags = re.UNICODE | (0 if case_sensitive else re.IGNORECASE)

    if match_type == "regex":
        try:
            pattern = re.compile(query, flags)
        except re.error as exc:
            return {"error": f"Invalid regex pattern: {exc}"}
    elif match_type == "exact":
        pattern = re.compile(r"\b" + re.escape(query) + r"\b", flags)
    elif match_type == "starts_with":
        pattern = re.compile(r"\b" + re.escape(query), flags)
    else:
        # contains (default)
        pattern = re.compile(re.escape(query), flags)

    matches: List[Dict[str, Any]] = []
    for m in pattern.finditer(full_text):
        if len(matches) >= max_results:
            break

        doc_start, doc_end = _text_range_to_doc_range(
            segments, m.start(), m.end()
        )

        match_entry: Dict[str, Any] = {
            "position": m.start(),
            "match": m.group(),
            "context": _extract_context(full_text, m.start(), m.end()),
        }
        if doc_start is not None:
            match_entry["documentIndex"] = doc_start
        if doc_end is not None:
            match_entry["documentEndIndex"] = doc_end

        matches.append(match_entry)

    return {
        "documentId": doc.get("documentId"),
        "title": doc.get("title"),
        "query": query,
        "matchCount": len(matches),
        "matches": matches,
    }


def register(registry: ToolRegistry) -> None:
    """Register all Docs read tools in the registry."""
    registry.register(
        name="get_document",
        description=(
            "Get the full structure and metadata of a Google Document, "
            "including body content, headers, footers, and styling."
        ),
        parameters=[
            ToolParameter(
                "document_id",
                "string",
                "The ID of the document (from URL)",
            ),
        ],
        tags=["docs", "read", "document", "content", "structure", "get"],
        fn=get_document,
        read_only=True,
    )

    registry.register(
        name="get_text",
        description=(
            "Extract plain text content from a Google Document. "
            "Returns the full text without formatting."
        ),
        parameters=[
            ToolParameter(
                "document_id",
                "string",
                "The ID of the document (from URL)",
            ),
        ],
        tags=["docs", "read", "text", "content", "plain", "extract"],
        fn=get_text,
        read_only=True,
    )

    registry.register(
        name="get_tables",
        description=(
            "Extract all tables from a Google Document with their content, "
            "dimensions, and positions."
        ),
        parameters=[
            ToolParameter(
                "document_id",
                "string",
                "The ID of the document (from URL)",
            ),
        ],
        tags=["docs", "read", "tables", "content", "extract", "data"],
        fn=get_tables,
        read_only=True,
    )

    registry.register(
        name="search_document",
        description=(
            "Search for text patterns within a Google Document. "
            "Supports substring, exact (whole-word), starts_with, and regex matching. "
            "Returns matching positions with surrounding context."
        ),
        parameters=[
            ToolParameter(
                "document_id",
                "string",
                "The ID of the document (from URL)",
            ),
            ToolParameter("query", "string", "Text or regex pattern to search for"),
            ToolParameter(
                "match_type",
                "string",
                "Matching strategy: contains (default), exact, starts_with, or regex.",
                required=False,
                default="contains",
            ),
            ToolParameter(
                "case_sensitive",
                "boolean",
                "Case-sensitive search (default: false)",
                required=False,
                default=False,
            ),
            ToolParameter(
                "max_results",
                "integer",
                "Max results to return (default: 50)",
                required=False,
                default=50,
            ),
        ],
        tags=["docs", "search", "find", "text", "query", "lookup", "regex"],
        fn=search_document,
        read_only=True,
    )

    registry.register(
        name="get_text_with_indices",
        description=(
            "Get document text annotated with character indices per segment "
            "(paragraph, heading, table). Each segment includes startIndex "
            "and endIndex for use with index-based editing tools like "
            "replace_text_in_range. Ideal for understanding document structure "
            "before making targeted edits."
        ),
        parameters=[
            ToolParameter(
                "document_id",
                "string",
                "The ID of the document (from URL)",
            ),
        ],
        tags=[
            "docs", "read", "text", "indices", "position",
            "structure", "segments", "map",
        ],
        fn=get_text_with_indices,
        read_only=True,
    )
