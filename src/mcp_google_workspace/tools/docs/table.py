"""Table operations for Google Docs."""

import re
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import Context

from ...registry import ToolParameter, ToolRegistry
from ._utils import pt, safe_batch_update, validate_document_id
from .read import _extract_text_from_elements

VALID_CONTENT_ALIGNMENTS = ["TOP", "MIDDLE", "BOTTOM"]
VALID_DASH_STYLES = ["SOLID", "DOT", "DASH"]


# Bounds for table dimensions (shared with format.py)
MAX_TABLE_ROWS = 100
MAX_TABLE_COLUMNS = 26

# Bounds for table cell operations
MAX_ROW_SPAN = 100
MAX_COLUMN_SPAN = 26
MAX_PADDING_PT = 144  # 2 inches
MAX_BORDER_WIDTH_PT = 24


def _cell_location(
    table_start_index: int, row_index: int, column_index: int
) -> Dict[str, Any]:
    """Build a TableCellLocation object."""
    return {
        "tableStartLocation": {"index": table_start_index},
        "rowIndex": row_index,
        "columnIndex": column_index,
    }


def _table_range(
    table_start_index: int,
    row_index: int,
    column_index: int,
    row_span: int,
    column_span: int,
) -> Dict[str, Any]:
    """Build a TableRange object."""
    return {
        "tableCellLocation": _cell_location(table_start_index, row_index, column_index),
        "rowSpan": row_span,
        "columnSpan": column_span,
    }


def update_table_cell_style(
    document_id: str,
    table_start_index: int,
    row_index: int,
    column_index: int,
    row_span: int = 1,
    column_span: int = 1,
    background_color: Optional[Dict[str, float]] = None,
    padding_top: Optional[float] = None,
    padding_bottom: Optional[float] = None,
    padding_left: Optional[float] = None,
    padding_right: Optional[float] = None,
    border_width: Optional[float] = None,
    border_color: Optional[Dict[str, float]] = None,
    border_dash_style: Optional[str] = None,
    content_alignment: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Update styling for one or more table cells.

    ``table_start_index`` is the character index where the table
    begins in the document body.  Use ``get_document`` or
    ``get_tables`` to find it.
    """
    if err := validate_document_id(document_id):
        return err

    for _name, _val in [
        ("padding_top", padding_top),
        ("padding_bottom", padding_bottom),
        ("padding_left", padding_left),
        ("padding_right", padding_right),
    ]:
        if _val is not None and (_val < 0 or _val > MAX_PADDING_PT):
            return {"error": f"{_name} must be between 0 and {MAX_PADDING_PT} PT"}

    if border_width is not None and (
        border_width < 0 or border_width > MAX_BORDER_WIDTH_PT
    ):
        return {"error": f"border_width must be between 0 and {MAX_BORDER_WIDTH_PT} PT"}

    style: Dict[str, Any] = {}
    fields: List[str] = []

    if background_color is not None:
        style["backgroundColor"] = {"color": {"rgbColor": background_color}}
        fields.append("backgroundColor")

    for name, value in [
        ("paddingTop", padding_top),
        ("paddingBottom", padding_bottom),
        ("paddingLeft", padding_left),
        ("paddingRight", padding_right),
    ]:
        if value is not None:
            style[name] = pt(value)
            fields.append(name)

    if (
        border_width is not None
        or border_color is not None
        or border_dash_style is not None
    ):
        border: Dict[str, Any] = {}
        if border_width is not None:
            border["width"] = pt(border_width)
        if border_color is not None:
            border["color"] = {"color": {"rgbColor": border_color}}
        if border_dash_style is not None:
            upper = border_dash_style.upper()
            if upper not in VALID_DASH_STYLES:
                return {
                    "error": (
                        f"Invalid border_dash_style '{border_dash_style}'. "
                        f"Must be one of: {', '.join(VALID_DASH_STYLES)}"
                    )
                }
            border["dashStyle"] = upper

        for side in ["borderTop", "borderBottom", "borderLeft", "borderRight"]:
            style[side] = border
            fields.append(side)

    if content_alignment is not None:
        upper = content_alignment.upper()
        if upper not in VALID_CONTENT_ALIGNMENTS:
            return {
                "error": (
                    f"Invalid content_alignment '{content_alignment}'. "
                    f"Must be one of: {', '.join(VALID_CONTENT_ALIGNMENTS)}"
                )
            }
        style["contentAlignment"] = upper
        fields.append("contentAlignment")

    if not fields:
        return {"error": "At least one cell style option must be provided"}

    docs_service = ctx.request_context.lifespan_context.docs_service

    requests = [
        {
            "updateTableCellStyle": {
                "tableRange": _table_range(
                    table_start_index,
                    row_index,
                    column_index,
                    row_span,
                    column_span,
                ),
                "tableCellStyle": style,
                "fields": ",".join(fields),
            }
        }
    ]

    result = safe_batch_update(docs_service, document_id, requests)
    if "error" in result:
        return result

    return {
        "documentId": document_id,
        "appliedStyles": fields,
        "replies": result.get("replies", []),
    }


def insert_table_row(
    document_id: str,
    table_start_index: int,
    row_index: int,
    insert_below: bool = True,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Insert a row into an existing table."""
    if err := validate_document_id(document_id):
        return err

    docs_service = ctx.request_context.lifespan_context.docs_service

    requests = [
        {
            "insertTableRow": {
                "tableCellLocation": _cell_location(table_start_index, row_index, 0),
                "insertBelow": insert_below,
            }
        }
    ]

    result = safe_batch_update(docs_service, document_id, requests)
    if "error" in result:
        return result

    return {
        "documentId": document_id,
        "insertedBelow": insert_below,
        "referenceRow": row_index,
        "replies": result.get("replies", []),
    }


def insert_table_column(
    document_id: str,
    table_start_index: int,
    column_index: int,
    insert_right: bool = True,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Insert a column into an existing table."""
    if err := validate_document_id(document_id):
        return err

    docs_service = ctx.request_context.lifespan_context.docs_service

    requests = [
        {
            "insertTableColumn": {
                "tableCellLocation": _cell_location(table_start_index, 0, column_index),
                "insertRight": insert_right,
            }
        }
    ]

    result = safe_batch_update(docs_service, document_id, requests)
    if "error" in result:
        return result

    return {
        "documentId": document_id,
        "insertedRight": insert_right,
        "referenceColumn": column_index,
        "replies": result.get("replies", []),
    }


def delete_table_row(
    document_id: str,
    table_start_index: int,
    row_index: int,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Delete a row from a table."""
    if err := validate_document_id(document_id):
        return err

    docs_service = ctx.request_context.lifespan_context.docs_service

    requests = [
        {
            "deleteTableRow": {
                "tableCellLocation": _cell_location(table_start_index, row_index, 0),
            }
        }
    ]

    result = safe_batch_update(docs_service, document_id, requests)
    if "error" in result:
        return result

    return {
        "documentId": document_id,
        "deletedRow": row_index,
        "replies": result.get("replies", []),
    }


def delete_table_column(
    document_id: str,
    table_start_index: int,
    column_index: int,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Delete a column from a table."""
    if err := validate_document_id(document_id):
        return err

    docs_service = ctx.request_context.lifespan_context.docs_service

    requests = [
        {
            "deleteTableColumn": {
                "tableCellLocation": _cell_location(table_start_index, 0, column_index),
            }
        }
    ]

    result = safe_batch_update(docs_service, document_id, requests)
    if "error" in result:
        return result

    return {
        "documentId": document_id,
        "deletedColumn": column_index,
        "replies": result.get("replies", []),
    }


def merge_table_cells(
    document_id: str,
    table_start_index: int,
    row_index: int,
    column_index: int,
    row_span: int,
    column_span: int,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Merge a rectangular range of table cells."""
    if err := validate_document_id(document_id):
        return err
    if row_span < 1 or column_span < 1:
        return {"error": "row_span and column_span must be at least 1"}
    if row_span > MAX_ROW_SPAN or column_span > MAX_COLUMN_SPAN:
        return {
            "error": (
                f"Maximum row_span is {MAX_ROW_SPAN}, "
                f"maximum column_span is {MAX_COLUMN_SPAN}"
            )
        }

    docs_service = ctx.request_context.lifespan_context.docs_service

    requests = [
        {
            "mergeTableCells": {
                "tableRange": _table_range(
                    table_start_index,
                    row_index,
                    column_index,
                    row_span,
                    column_span,
                ),
            }
        }
    ]

    result = safe_batch_update(docs_service, document_id, requests)
    if "error" in result:
        return result

    return {
        "documentId": document_id,
        "mergedRange": {
            "rowIndex": row_index,
            "columnIndex": column_index,
            "rowSpan": row_span,
            "columnSpan": column_span,
        },
        "replies": result.get("replies", []),
    }


def unmerge_table_cells(
    document_id: str,
    table_start_index: int,
    row_index: int,
    column_index: int,
    row_span: int,
    column_span: int,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Unmerge previously merged table cells."""
    if err := validate_document_id(document_id):
        return err
    if row_span < 1 or column_span < 1:
        return {"error": "row_span and column_span must be at least 1"}
    if row_span > MAX_ROW_SPAN or column_span > MAX_COLUMN_SPAN:
        return {
            "error": (
                f"Maximum row_span is {MAX_ROW_SPAN}, "
                f"maximum column_span is {MAX_COLUMN_SPAN}"
            )
        }

    docs_service = ctx.request_context.lifespan_context.docs_service

    requests = [
        {
            "unmergeTableCells": {
                "tableRange": _table_range(
                    table_start_index,
                    row_index,
                    column_index,
                    row_span,
                    column_span,
                ),
            }
        }
    ]

    result = safe_batch_update(docs_service, document_id, requests)
    if "error" in result:
        return result

    return {
        "documentId": document_id,
        "unmergedRange": {
            "rowIndex": row_index,
            "columnIndex": column_index,
            "rowSpan": row_span,
            "columnSpan": column_span,
        },
        "replies": result.get("replies", []),
    }


VALID_WIDTH_TYPES = ["EVENLY_DISTRIBUTED", "FIXED_WIDTH"]
MAX_COLUMN_WIDTH_PT = 2000
MAX_ROW_HEIGHT_PT = 2000
MAX_PINNED_ROWS = 100


def update_table_column_properties(
    document_id: str,
    table_start_index: int,
    column_indices: List[int],
    width: Optional[float] = None,
    width_type: str = "FIXED_WIDTH",
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Update column properties (width) for specific columns in a table.

    ``table_start_index`` is the character index where the table
    begins in the document body.  Use ``get_tables`` to find it.
    """
    if err := validate_document_id(document_id):
        return err

    if not column_indices:
        return {"error": "column_indices must be a non-empty list"}
    if any(i < 0 for i in column_indices):
        return {"error": "All column_indices must be non-negative"}

    upper_type = width_type.upper()
    if upper_type not in VALID_WIDTH_TYPES:
        return {
            "error": (
                f"Invalid width_type '{width_type}'. "
                f"Must be one of: {', '.join(VALID_WIDTH_TYPES)}"
            )
        }

    if width is not None and (width <= 0 or width > MAX_COLUMN_WIDTH_PT):
        return {"error": f"width must be between 0 and {MAX_COLUMN_WIDTH_PT} PT"}

    props: Dict[str, Any] = {"widthType": upper_type}
    fields: List[str] = ["widthType"]

    if width is not None:
        props["width"] = pt(width)
        fields.append("width")

    docs_service = ctx.request_context.lifespan_context.docs_service

    requests = [
        {
            "updateTableColumnProperties": {
                "tableStartLocation": {"index": table_start_index},
                "columnIndices": column_indices,
                "tableColumnProperties": props,
                "fields": ",".join(fields),
            }
        }
    ]

    result = safe_batch_update(docs_service, document_id, requests)
    if "error" in result:
        return result

    return {
        "documentId": document_id,
        "columnIndices": column_indices,
        "appliedProperties": fields,
        "replies": result.get("replies", []),
    }


def update_table_row_style(
    document_id: str,
    table_start_index: int,
    row_indices: List[int],
    min_row_height: Optional[float] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Update row style (minimum height) for specific rows in a table.

    ``table_start_index`` is the character index where the table
    begins.  Use ``get_tables`` to find it.
    """
    if err := validate_document_id(document_id):
        return err

    if not row_indices:
        return {"error": "row_indices must be a non-empty list"}
    if any(i < 0 for i in row_indices):
        return {"error": "All row_indices must be non-negative"}

    if min_row_height is not None and (
        min_row_height < 0 or min_row_height > MAX_ROW_HEIGHT_PT
    ):
        return {"error": f"min_row_height must be between 0 and {MAX_ROW_HEIGHT_PT} PT"}

    style: Dict[str, Any] = {}
    fields: List[str] = []

    if min_row_height is not None:
        style["minRowHeight"] = pt(min_row_height)
        fields.append("minRowHeight")

    if not fields:
        return {"error": "At least one row style option must be provided"}

    docs_service = ctx.request_context.lifespan_context.docs_service

    requests = [
        {
            "updateTableRowStyle": {
                "tableStartLocation": {"index": table_start_index},
                "rowIndices": row_indices,
                "tableRowStyle": style,
                "fields": ",".join(fields),
            }
        }
    ]

    result = safe_batch_update(docs_service, document_id, requests)
    if "error" in result:
        return result

    return {
        "documentId": document_id,
        "rowIndices": row_indices,
        "appliedStyles": fields,
        "replies": result.get("replies", []),
    }


def pin_table_header_rows(
    document_id: str,
    table_start_index: int,
    pinned_header_row_count: int = 1,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Pin rows as header rows in a table.

    Pinned header rows repeat at the top of the table when it
    spans multiple pages.  Set ``pinned_header_row_count`` to 0
    to unpin all header rows.
    """
    if err := validate_document_id(document_id):
        return err

    if pinned_header_row_count < 0 or pinned_header_row_count > MAX_PINNED_ROWS:
        return {
            "error": (
                f"pinned_header_row_count must be between 0 and {MAX_PINNED_ROWS}"
            )
        }

    docs_service = ctx.request_context.lifespan_context.docs_service

    requests = [
        {
            "pinTableHeaderRows": {
                "tableStartLocation": {"index": table_start_index},
                "pinnedHeaderRowsCount": pinned_header_row_count,
            }
        }
    ]

    result = safe_batch_update(docs_service, document_id, requests)
    if "error" in result:
        return result

    return {
        "documentId": document_id,
        "tableStartIndex": table_start_index,
        "pinnedHeaderRowCount": pinned_header_row_count,
        "replies": result.get("replies", []),
    }


def _find_table_element(
    content: List[Dict[str, Any]], table_start_index: int
) -> Optional[Dict[str, Any]]:
    """Find the table structural element at the given start index."""
    for element in content:
        if "table" in element and element.get("startIndex") == table_start_index:
            return element
    return None


def _get_cell_content_range(
    table_element: Dict[str, Any], row_index: int, column_index: int
) -> tuple:
    """Extract (content_start, content_end, cell_text) for a specific cell.

    Returns ``(start_index, end_index, text)`` from the cell's internal
    paragraph elements, or ``(None, None, None)`` if the cell is not found.
    """
    table = table_element.get("table", {})
    rows = table.get("tableRows", [])
    if row_index < 0 or row_index >= len(rows):
        return None, None, None

    cells = rows[row_index].get("tableCells", [])
    if column_index < 0 or column_index >= len(cells):
        return None, None, None

    cell_content = cells[column_index].get("content", [])
    if not cell_content:
        return None, None, None

    # Cell content is a list of structural elements (paragraphs).
    # The content range spans from the first element's startIndex
    # to the last element's endIndex.
    c_start = cell_content[0].get("startIndex")
    c_end = cell_content[-1].get("endIndex")

    # Extract cell text for find operations
    cell_text = _extract_text_from_elements(cell_content)

    return c_start, c_end, cell_text


def _build_partial_replace_requests(
    table_element: Dict[str, Any],
    row_index: int,
    column_index: int,
    cell_text: str,
    find_text: str,
    replacement_text: str,
    match_case: bool,
) -> Optional[List[Dict[str, Any]]]:
    """Build requests that replace the first occurrence of *find_text* in a cell.

    Returns ``None`` when no match is found (caller should emit a
    ``found: False`` response).  Returns an empty list when a match is
    found but no actual mutations are needed.

    Raises
    ------
    ValueError
        If the matched text range cannot be mapped back to document indices.
    """
    flags = re.UNICODE | (0 if match_case else re.IGNORECASE)
    pattern = re.compile(re.escape(find_text), flags)
    match = pattern.search(cell_text)

    if not match:
        return None

    cell_content = (
        table_element["table"]["tableRows"][row_index]["tableCells"][
            column_index
        ].get("content", [])
    )

    from .read import _extract_text_with_positions, _text_range_to_doc_range

    _cell_text, cell_segs = _extract_text_with_positions(cell_content)
    doc_start, doc_end = _text_range_to_doc_range(
        cell_segs, match.start(), match.end()
    )

    if doc_start is None or doc_end is None:
        raise ValueError("Cannot map find_text position to document indices")

    requests: List[Dict[str, Any]] = [
        {
            "deleteContentRange": {
                "range": {"startIndex": doc_start, "endIndex": doc_end}
            }
        }
    ]
    if replacement_text:
        requests.append(
            {
                "insertText": {
                    "location": {"index": doc_start},
                    "text": replacement_text,
                }
            }
        )
    return requests


def _build_full_replace_requests(
    c_start: int,
    c_end: int,
    replacement_text: str,
) -> List[Dict[str, Any]]:
    """Build requests that replace the entire cell content.

    Preserves the mandatory trailing newline by deleting up to
    ``c_end - 1``.
    """
    requests: List[Dict[str, Any]] = []
    delete_end = c_end - 1 if c_end > c_start else c_end
    if delete_end > c_start:
        requests.append(
            {
                "deleteContentRange": {
                    "range": {"startIndex": c_start, "endIndex": delete_end}
                }
            }
        )
    if replacement_text:
        requests.append(
            {
                "insertText": {
                    "location": {"index": c_start},
                    "text": replacement_text,
                }
            }
        )
    return requests


def update_table_cell_content(
    document_id: str,
    table_start_index: int,
    row_index: int,
    column_index: int,
    replacement_text: str,
    find_text: Optional[str] = None,
    match_case: bool = False,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Replace content in a specific table cell.

    If ``find_text`` is provided, only the first occurrence of that text
    within the cell is replaced.  Otherwise the **entire** cell content
    is replaced (preserving the mandatory trailing newline).

    This tool eliminates the manual workflow of parsing raw JSON to
    find cell indices and issuing separate delete+insert requests.
    """
    if err := validate_document_id(document_id):
        return err

    docs_service = ctx.request_context.lifespan_context.docs_service

    doc = docs_service.documents().get(documentId=document_id).execute()
    body = doc.get("body", {})
    content = body.get("content", [])

    table_element = _find_table_element(content, table_start_index)
    if table_element is None:
        return {"error": f"No table found at startIndex {table_start_index}"}

    c_start, c_end, cell_text = _get_cell_content_range(
        table_element, row_index, column_index
    )
    if c_start is None or c_end is None:
        return {
            "error": (
                f"Cell [{row_index}, {column_index}] not found or has no "
                f"content indices"
            )
        }

    cell_ref = {"row": row_index, "column": column_index}

    if find_text is not None:
        if not find_text:
            return {"error": "find_text must not be empty when provided"}

        try:
            requests = _build_partial_replace_requests(
                table_element, row_index, column_index,
                cell_text, find_text, replacement_text, match_case,
            )
        except ValueError as e:
            return {"error": str(e)}

        if requests is None:
            return {
                "documentId": document_id,
                "cell": cell_ref,
                "findText": find_text,
                "found": False,
            }
    else:
        requests = _build_full_replace_requests(c_start, c_end, replacement_text)

    if not requests:
        return {
            "documentId": document_id,
            "cell": cell_ref,
            "replaced": False,
            "reason": "No changes needed (empty content, empty replacement)",
        }

    result = safe_batch_update(docs_service, document_id, requests)
    if "error" in result:
        return result

    return {
        "documentId": document_id,
        "cell": cell_ref,
        "replaced": True,
        "replacementText": replacement_text,
        "findText": find_text,
        "replies": result.get("replies", []),
    }


def _get_all_cell_start_indices(
    table_element: Dict[str, Any],
) -> List[List[Optional[int]]]:
    """Extract start indices for every cell in a table.

    Returns a 2D list ``[row][col]`` of start indices (or ``None``
    for cells whose index cannot be determined).
    """
    table = table_element.get("table", {})
    rows = table.get("tableRows", [])
    result: List[List[Optional[int]]] = []
    for row in rows:
        row_indices: List[Optional[int]] = []
        for cell in row.get("tableCells", []):
            cell_content = cell.get("content", [])
            start_idx: Optional[int] = None
            if cell_content:
                # First paragraph element's first text element startIndex
                for content_elem in cell_content:
                    para = content_elem.get("paragraph")
                    if para:
                        elements = para.get("elements", [])
                        if elements:
                            start_idx = elements[0].get("startIndex")
                            break
            row_indices.append(start_idx)
        result.append(row_indices)
    return result


# Maximum cells in a single populate_table call
MAX_POPULATE_CELLS = 2600  # 100 rows * 26 cols


def populate_table(
    document_id: str,
    table_start_index: int,
    data: List[List[str]],
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Populate multiple table cells in a single batch operation.

    Accepts a 2D array of strings.  Each element ``data[row][col]``
    is inserted into the corresponding cell.  Empty strings are
    skipped.  Cells outside the table dimensions are ignored.

    This replaces the need to call ``update_table_cell_content``
    once per cell — a 10x10 table goes from ~100 API calls to 2
    (1 read + 1 batch write).
    """
    if err := validate_document_id(document_id):
        return err

    if not data:
        return {"error": "data must be a non-empty 2D array"}

    total_cells = sum(len(row) for row in data)
    if total_cells > MAX_POPULATE_CELLS:
        return {
            "error": (
                f"Too many cells ({total_cells}). "
                f"Maximum is {MAX_POPULATE_CELLS}."
            )
        }

    docs_service = ctx.request_context.lifespan_context.docs_service

    # 1. Read document to find cell indices
    doc = docs_service.documents().get(documentId=document_id).execute()
    body = doc.get("body", {})
    content = body.get("content", [])

    table_element = _find_table_element(content, table_start_index)
    if table_element is None:
        return {"error": f"No table found at startIndex {table_start_index}"}

    table = table_element.get("table", {})
    table_rows = len(table.get("tableRows", []))
    table_cols = table.get("columns", 0)
    cell_indices = _get_all_cell_start_indices(table_element)

    # 2. Build insertText requests in reverse order (last cell first)
    #    to avoid index shifts from earlier insertions.
    requests: List[Dict[str, Any]] = []
    cells_written = 0
    skipped_cells: List[List[int]] = []

    for ri in range(min(len(data), table_rows) - 1, -1, -1):
        row_data = data[ri]
        for ci in range(min(len(row_data), table_cols) - 1, -1, -1):
            text = row_data[ci]
            if not text:
                continue

            if ri < len(cell_indices) and ci < len(cell_indices[ri]):
                start_idx = cell_indices[ri][ci]
            else:
                start_idx = None

            if start_idx is None:
                skipped_cells.append([ri, ci])
                continue

            requests.append(
                {
                    "insertText": {
                        "location": {"index": start_idx},
                        "text": str(text),
                    }
                }
            )
            cells_written += 1

    if not requests:
        return {
            "documentId": document_id,
            "cellsWritten": 0,
            "reason": "No non-empty cells to write",
        }

    # 3. Execute single batch
    result = safe_batch_update(docs_service, document_id, requests)
    if "error" in result:
        return result

    response: Dict[str, Any] = {
        "documentId": document_id,
        "tableStartIndex": table_start_index,
        "cellsWritten": cells_written,
        "tableSize": {"rows": table_rows, "columns": table_cols},
        "replies": result.get("replies", []),
    }
    if skipped_cells:
        response["skippedCells"] = skipped_cells
    return response


def _find_nearest_table(
    content: List[Dict[str, Any]],
    target_index: int,
    max_distance: int = 20,
) -> Optional[Dict[str, Any]]:
    """Find the table element closest to *target_index*.

    Returns ``None`` when no table is within *max_distance* of
    the target index.
    """
    best: Optional[Dict[str, Any]] = None
    best_dist = float("inf")
    for elem in content:
        if "table" not in elem:
            continue
        dist = abs(elem.get("startIndex", 0) - target_index)
        if dist < best_dist:
            best_dist = dist
            best = elem
    if best is None or best_dist >= max_distance:
        return None
    return best


def _build_normalize_style_requests(
    table_element: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Build requests that reset all cell paragraph styles to NORMAL_TEXT.

    Without this, cells inherit the paragraph style from the insertion
    context (e.g. HEADING_1), causing unexpectedly large text.
    """
    requests: List[Dict[str, Any]] = []
    for row in table_element.get("table", {}).get("tableRows", []):
        for cell in row.get("tableCells", []):
            cell_content = cell.get("content", [])
            if cell_content:
                cs = cell_content[0].get("startIndex")
                ce = cell_content[-1].get("endIndex")
                if cs is not None and ce is not None and ce > cs:
                    requests.append(
                        {
                            "updateParagraphStyle": {
                                "range": {"startIndex": cs, "endIndex": ce},
                                "paragraphStyle": {
                                    "namedStyleType": "NORMAL_TEXT"
                                },
                                "fields": "namedStyleType",
                            }
                        }
                    )
    return requests


def _build_populate_requests(
    data: List[List[str]],
    rows: int,
    columns: int,
    cell_indices: List[List[Optional[int]]],
) -> tuple:
    """Build insertText requests in reverse order for cell population.

    Returns ``(text_requests, cells_written, skipped_cells)``.
    """
    text_requests: List[Dict[str, Any]] = []
    cells_written = 0
    skipped_cells: List[List[int]] = []

    for ri in range(rows - 1, -1, -1):
        row_data = data[ri]
        for ci in range(columns - 1, -1, -1):
            if ci >= len(row_data):
                continue
            text = row_data[ci]
            if not text:
                continue

            if ri < len(cell_indices) and ci < len(cell_indices[ri]):
                start_idx = cell_indices[ri][ci]
            else:
                start_idx = None

            if start_idx is None:
                skipped_cells.append([ri, ci])
                continue

            text_requests.append(
                {
                    "insertText": {
                        "location": {"index": start_idx},
                        "text": str(text),
                    }
                }
            )
            cells_written += 1

    return text_requests, cells_written, skipped_cells


def insert_populated_table(
    document_id: str,
    data: List[List[str]],
    index: int = 1,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Insert a new table pre-filled with data in a single operation.

    Infers row count and column count from ``data`` dimensions.
    Combines ``insert_table`` + ``populate_table`` into one tool call.

    This is the recommended way to add data tables to documents —
    one call instead of N+1 separate API calls.
    """
    if err := validate_document_id(document_id):
        return err

    if not data:
        return {"error": "data must be a non-empty 2D array"}

    rows = len(data)
    columns = max(len(row) for row in data) if data else 0
    if columns == 0:
        return {"error": "data must contain at least one non-empty row"}

    if rows > MAX_TABLE_ROWS:
        return {"error": f"Maximum {MAX_TABLE_ROWS} rows allowed"}
    if columns > MAX_TABLE_COLUMNS:
        return {"error": f"Maximum {MAX_TABLE_COLUMNS} columns allowed"}

    total_cells = sum(len(row) for row in data)
    if total_cells > MAX_POPULATE_CELLS:
        return {
            "error": (
                f"Too many cells ({total_cells}). "
                f"Maximum is {MAX_POPULATE_CELLS}."
            )
        }

    docs_service = ctx.request_context.lifespan_context.docs_service

    # 1. Insert the empty table
    insert_result = safe_batch_update(
        docs_service,
        document_id,
        [
            {
                "insertTable": {
                    "rows": rows,
                    "columns": columns,
                    "location": {"index": index},
                }
            }
        ],
    )
    if "error" in insert_result:
        return insert_result

    # 2. Locate the newly inserted table
    doc = docs_service.documents().get(documentId=document_id).execute()
    content = doc.get("body", {}).get("content", [])

    table_element = _find_nearest_table(content, index)
    if table_element is None:
        return {
            "documentId": document_id,
            "rows": rows,
            "columns": columns,
            "insertedAt": index,
            "warning": "Table inserted but could not locate it for cell population",
            "cellsWritten": 0,
        }

    actual_start = table_element.get("startIndex", index)
    cell_indices = _get_all_cell_start_indices(table_element)

    # 3. Build batch: normalize styles then populate text
    normalize_requests = _build_normalize_style_requests(table_element)
    text_requests, cells_written, skipped_cells = _build_populate_requests(
        data, rows, columns, cell_indices,
    )

    requests = normalize_requests + text_requests
    if requests:
        pop_result = safe_batch_update(docs_service, document_id, requests)
        if "error" in pop_result:
            return {
                "documentId": document_id,
                "rows": rows,
                "columns": columns,
                "insertedAt": index,
                "tableStartIndex": actual_start,
                "warning": f"Table inserted but population failed: {pop_result['error']}",
                "cellsWritten": 0,
            }

    response: Dict[str, Any] = {
        "documentId": document_id,
        "rows": rows,
        "columns": columns,
        "insertedAt": index,
        "tableStartIndex": actual_start,
        "cellsWritten": cells_written,
    }
    if skipped_cells:
        response["skippedCells"] = skipped_cells
    return response


def clone_table(
    document_id: str,
    table_start_index: int,
    destination_index: int,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Clone an existing table and insert the copy at a new position.

    Reads the source table's text content and inserts a new pre-filled
    table at ``destination_index``.  Formatting is not cloned — only
    cell text values are copied.  Use ``update_table_cell_style`` and
    ``update_table_column_properties`` afterward to re-apply styles.

    Use ``get_tables`` to find ``table_start_index``.
    """
    if err := validate_document_id(document_id):
        return err

    docs_service = ctx.request_context.lifespan_context.docs_service

    doc = docs_service.documents().get(documentId=document_id).execute()
    body = doc.get("body", {})
    content = body.get("content", [])

    table_element = _find_table_element(content, table_start_index)
    if table_element is None:
        return {"error": f"No table found at startIndex {table_start_index}"}

    table = table_element.get("table", {})
    table_rows_raw = table.get("tableRows", [])
    columns = table.get("columns", 0)
    rows = len(table_rows_raw)

    if rows == 0 or columns == 0:
        return {"error": "Source table is empty"}
    if rows > MAX_TABLE_ROWS or columns > MAX_TABLE_COLUMNS:
        return {
            "error": (
                f"Table dimensions {rows}x{columns} exceed "
                f"maximum {MAX_TABLE_ROWS}x{MAX_TABLE_COLUMNS}"
            )
        }

    # Extract cell text data
    data: List[List[str]] = []
    for row in table_rows_raw:
        row_data: List[str] = []
        for cell in row.get("tableCells", []):
            cell_content = cell.get("content", [])
            row_data.append(_extract_text_from_elements(cell_content).rstrip("\n"))
        data.append(row_data)

    # Insert empty table at destination
    insert_result = safe_batch_update(
        docs_service,
        document_id,
        [
            {
                "insertTable": {
                    "rows": rows,
                    "columns": columns,
                    "location": {"index": destination_index},
                }
            }
        ],
    )
    if "error" in insert_result:
        return insert_result

    # Re-read to find the new table
    doc2 = docs_service.documents().get(documentId=document_id).execute()
    body2 = doc2.get("body", {})
    content2 = body2.get("content", [])

    new_table_element = None
    best_dist = float("inf")
    for elem in content2:
        if "table" not in elem:
            continue
        dist = abs(elem.get("startIndex", 0) - destination_index)
        if dist < best_dist:
            best_dist = dist
            new_table_element = elem

    if new_table_element is None or best_dist >= 20:
        return {
            "documentId": document_id,
            "clonedFrom": table_start_index,
            "insertedAt": destination_index,
            "rows": rows,
            "columns": columns,
            "warning": "Table inserted but could not locate for population",
            "cellsWritten": 0,
        }

    actual_start = new_table_element.get("startIndex", destination_index)
    cell_indices = _get_all_cell_start_indices(new_table_element)

    # Build populate requests in reverse order
    text_requests: List[Dict[str, Any]] = []
    cells_written = 0

    for ri in range(rows - 1, -1, -1):
        row_data = data[ri]
        for ci in range(columns - 1, -1, -1):
            if ci >= len(row_data):
                continue
            text = row_data[ci]
            if not text:
                continue
            if ri < len(cell_indices) and ci < len(cell_indices[ri]):
                start_idx = cell_indices[ri][ci]
            else:
                start_idx = None
            if start_idx is None:
                continue
            text_requests.append(
                {"insertText": {"location": {"index": start_idx}, "text": text}}
            )
            cells_written += 1

    if text_requests:
        pop_result = safe_batch_update(docs_service, document_id, text_requests)
        if "error" in pop_result:
            return {
                "documentId": document_id,
                "clonedFrom": table_start_index,
                "tableStartIndex": actual_start,
                "warning": f"Table inserted but population failed: {pop_result['error']}",
                "cellsWritten": 0,
            }

    return {
        "documentId": document_id,
        "clonedFrom": table_start_index,
        "tableStartIndex": actual_start,
        "insertedAt": destination_index,
        "rows": rows,
        "columns": columns,
        "cellsWritten": cells_written,
    }


def register(registry: ToolRegistry) -> None:
    """Register all Docs table tools in the registry."""
    registry.register(
        name="update_table_cell_style",
        description=(
            "Update table cell styling: background color, padding, "
            "borders, and vertical content alignment. "
            "Use get_tables to find table_start_index."
        ),
        parameters=[
            ToolParameter("document_id", "string", "The ID of the document (from URL)"),
            ToolParameter(
                "table_start_index",
                "integer",
                "Character index where the table starts in the document",
            ),
            ToolParameter("row_index", "integer", "Zero-based row index"),
            ToolParameter("column_index", "integer", "Zero-based column index"),
            ToolParameter(
                "row_span",
                "integer",
                "Number of rows to style (default: 1)",
                required=False,
                default=1,
            ),
            ToolParameter(
                "column_span",
                "integer",
                "Number of columns to style (default: 1)",
                required=False,
                default=1,
            ),
            ToolParameter(
                "background_color",
                "object",
                "Cell background as {red, green, blue} 0.0-1.0",
                required=False,
            ),
            ToolParameter("padding_top", "number", "Top padding in PT", required=False),
            ToolParameter(
                "padding_bottom", "number", "Bottom padding in PT", required=False
            ),
            ToolParameter(
                "padding_left", "number", "Left padding in PT", required=False
            ),
            ToolParameter(
                "padding_right", "number", "Right padding in PT", required=False
            ),
            ToolParameter(
                "border_width",
                "number",
                "Border width in PT (applies to all sides)",
                required=False,
            ),
            ToolParameter(
                "border_color",
                "object",
                "Border color as {red, green, blue} 0.0-1.0",
                required=False,
            ),
            ToolParameter(
                "border_dash_style",
                "string",
                "Border style: SOLID, DOT, or DASH",
                required=False,
            ),
            ToolParameter(
                "content_alignment",
                "string",
                "Vertical alignment: TOP, MIDDLE, or BOTTOM",
                required=False,
            ),
        ],
        tags=["docs", "table", "cell", "style", "border", "padding", "background"],
        fn=update_table_cell_style,
    )

    registry.register(
        name="insert_table_row",
        description="Insert a row above or below a reference row in a table.",
        parameters=[
            ToolParameter("document_id", "string", "The ID of the document (from URL)"),
            ToolParameter(
                "table_start_index",
                "integer",
                "Character index where the table starts",
            ),
            ToolParameter("row_index", "integer", "Zero-based reference row index"),
            ToolParameter(
                "insert_below",
                "boolean",
                "Insert below (true) or above (false) the reference row "
                "(default: true)",
                required=False,
                default=True,
            ),
        ],
        tags=["docs", "table", "row", "insert", "add"],
        fn=insert_table_row,
    )

    registry.register(
        name="insert_table_column",
        description=("Insert a column to the left or right of a reference column."),
        parameters=[
            ToolParameter("document_id", "string", "The ID of the document (from URL)"),
            ToolParameter(
                "table_start_index",
                "integer",
                "Character index where the table starts",
            ),
            ToolParameter(
                "column_index", "integer", "Zero-based reference column index"
            ),
            ToolParameter(
                "insert_right",
                "boolean",
                "Insert right (true) or left (false) of reference column "
                "(default: true)",
                required=False,
                default=True,
            ),
        ],
        tags=["docs", "table", "column", "insert", "add"],
        fn=insert_table_column,
    )

    registry.register(
        name="delete_table_row",
        description="Delete a row from a table by row index.",
        parameters=[
            ToolParameter("document_id", "string", "The ID of the document (from URL)"),
            ToolParameter(
                "table_start_index",
                "integer",
                "Character index where the table starts",
            ),
            ToolParameter("row_index", "integer", "Zero-based row index to delete"),
        ],
        tags=["docs", "table", "row", "delete", "remove"],
        fn=delete_table_row,
    )

    registry.register(
        name="delete_table_column",
        description="Delete a column from a table by column index.",
        parameters=[
            ToolParameter("document_id", "string", "The ID of the document (from URL)"),
            ToolParameter(
                "table_start_index",
                "integer",
                "Character index where the table starts",
            ),
            ToolParameter(
                "column_index", "integer", "Zero-based column index to delete"
            ),
        ],
        tags=["docs", "table", "column", "delete", "remove"],
        fn=delete_table_column,
    )

    registry.register(
        name="merge_table_cells",
        description=(
            "Merge a rectangular range of table cells. "
            "Text from merged cells concatenates into the top-left cell."
        ),
        parameters=[
            ToolParameter("document_id", "string", "The ID of the document (from URL)"),
            ToolParameter(
                "table_start_index",
                "integer",
                "Character index where the table starts",
            ),
            ToolParameter("row_index", "integer", "Top-left cell row (zero-based)"),
            ToolParameter(
                "column_index", "integer", "Top-left cell column (zero-based)"
            ),
            ToolParameter("row_span", "integer", "Number of rows to merge"),
            ToolParameter("column_span", "integer", "Number of columns to merge"),
        ],
        tags=["docs", "table", "merge", "cells", "combine", "span"],
        fn=merge_table_cells,
    )

    registry.register(
        name="unmerge_table_cells",
        description="Unmerge previously merged table cells back to individual cells.",
        parameters=[
            ToolParameter("document_id", "string", "The ID of the document (from URL)"),
            ToolParameter(
                "table_start_index",
                "integer",
                "Character index where the table starts",
            ),
            ToolParameter("row_index", "integer", "Top-left cell row (zero-based)"),
            ToolParameter(
                "column_index", "integer", "Top-left cell column (zero-based)"
            ),
            ToolParameter("row_span", "integer", "Number of rows in range"),
            ToolParameter("column_span", "integer", "Number of columns in range"),
        ],
        tags=["docs", "table", "unmerge", "cells", "split"],
        fn=unmerge_table_cells,
    )

    registry.register(
        name="update_table_column_properties",
        description=(
            "Update table column properties: width and width type. "
            "Use get_tables to find table_start_index."
        ),
        parameters=[
            ToolParameter("document_id", "string", "The ID of the document (from URL)"),
            ToolParameter(
                "table_start_index",
                "integer",
                "Character index where the table starts in the document",
            ),
            ToolParameter(
                "column_indices",
                "array",
                "List of zero-based column indices to update",
            ),
            ToolParameter(
                "width",
                "number",
                "Column width in points (72 PT = 1 inch)",
                required=False,
            ),
            ToolParameter(
                "width_type",
                "string",
                "Width type: FIXED_WIDTH or EVENLY_DISTRIBUTED (default: FIXED_WIDTH)",
                required=False,
                default="FIXED_WIDTH",
            ),
        ],
        tags=["docs", "table", "column", "width", "properties", "resize"],
        fn=update_table_column_properties,
    )

    registry.register(
        name="update_table_row_style",
        description=(
            "Update table row style: minimum row height. "
            "Use get_tables to find table_start_index."
        ),
        parameters=[
            ToolParameter("document_id", "string", "The ID of the document (from URL)"),
            ToolParameter(
                "table_start_index",
                "integer",
                "Character index where the table starts in the document",
            ),
            ToolParameter(
                "row_indices",
                "array",
                "List of zero-based row indices to update",
            ),
            ToolParameter(
                "min_row_height",
                "number",
                "Minimum row height in points (72 PT = 1 inch)",
                required=False,
            ),
        ],
        tags=["docs", "table", "row", "height", "style", "resize"],
        fn=update_table_row_style,
    )

    registry.register(
        name="pin_table_header_rows",
        description=(
            "Pin rows as repeating header rows in a table. "
            "Pinned rows repeat at the top when the table spans pages. "
            "Set count to 0 to unpin."
        ),
        parameters=[
            ToolParameter("document_id", "string", "The ID of the document (from URL)"),
            ToolParameter(
                "table_start_index",
                "integer",
                "Character index where the table starts in the document",
            ),
            ToolParameter(
                "pinned_header_row_count",
                "integer",
                "Number of rows to pin as headers (0 to unpin, default: 1)",
                required=False,
                default=1,
            ),
        ],
        tags=["docs", "table", "header", "pin", "repeat", "freeze"],
        fn=pin_table_header_rows,
    )

    registry.register(
        name="update_table_cell_content",
        description=(
            "Replace the text content of a specific table cell. "
            "If find_text is provided, only the first occurrence within the "
            "cell is replaced. Otherwise the entire cell content is replaced. "
            "Use get_tables to find table_start_index. "
            "Much safer than manual delete_content+insert_text for table cells."
        ),
        parameters=[
            ToolParameter("document_id", "string", "The ID of the document (from URL)"),
            ToolParameter(
                "table_start_index",
                "integer",
                "Character index where the table starts (from get_tables)",
            ),
            ToolParameter("row_index", "integer", "Zero-based row index"),
            ToolParameter("column_index", "integer", "Zero-based column index"),
            ToolParameter(
                "replacement_text",
                "string",
                "New text to insert in the cell",
            ),
            ToolParameter(
                "find_text",
                "string",
                "Optional: text to find within the cell for partial replace. "
                "If omitted, replaces entire cell content.",
                required=False,
            ),
            ToolParameter(
                "match_case",
                "boolean",
                "Case-sensitive matching for find_text (default: false)",
                required=False,
                default=False,
            ),
        ],
        tags=[
            "docs", "table", "cell", "content", "replace", "update",
            "text", "edit", "write",
        ],
        fn=update_table_cell_content,
    )

    registry.register(
        name="populate_table",
        description=(
            "Populate multiple table cells in a single batch operation. "
            "Accepts a 2D array of strings — each element data[row][col] "
            "is written to the corresponding cell. Empty strings are skipped. "
            "RECOMMENDED: use this instead of calling update_table_cell_content "
            "per cell — a 10x10 table goes from ~100 API calls to 2."
        ),
        parameters=[
            ToolParameter("document_id", "string", "The ID of the document (from URL)"),
            ToolParameter(
                "table_start_index",
                "integer",
                "Character index where the table starts (from get_tables)",
            ),
            ToolParameter(
                "data",
                "array",
                "2D array of strings: [[row0col0, row0col1, ...], [row1col0, ...]]. "
                "Empty strings are skipped. Rows/cols beyond table size are ignored.",
            ),
        ],
        tags=[
            "docs", "table", "populate", "fill", "batch", "cells",
            "bulk", "data", "write", "efficient",
        ],
        fn=populate_table,
    )

    registry.register(
        name="insert_populated_table",
        description=(
            "Insert a new table pre-filled with data in one operation. "
            "Infers rows and columns from data dimensions. "
            "RECOMMENDED: use this instead of insert_table + populate_table "
            "separately — one tool call creates and fills the entire table. "
            "Ideal for reports, data summaries, and structured content."
        ),
        parameters=[
            ToolParameter("document_id", "string", "The ID of the document (from URL)"),
            ToolParameter(
                "data",
                "array",
                "2D array of strings: [[row0col0, row0col1, ...], [row1col0, ...]]. "
                "First row is typically headers. Empty strings create empty cells. "
                "Row count and column count are inferred from the array shape.",
            ),
            ToolParameter(
                "index",
                "integer",
                "Character index to insert table at (1 = start, default: 1)",
                required=False,
                default=1,
            ),
        ],
        tags=[
            "docs", "table", "insert", "populate", "create", "fill",
            "batch", "data", "efficient", "report", "grid",
        ],
        fn=insert_populated_table,
    )

    registry.register(
        name="clone_table",
        description=(
            "Clone an existing table and insert the copy at a new position. "
            "Copies cell text content only — formatting is not cloned. "
            "Use get_tables to find table_start_index."
        ),
        parameters=[
            ToolParameter("document_id", "string", "The ID of the document (from URL)"),
            ToolParameter(
                "table_start_index",
                "integer",
                "Character index where the source table starts (from get_tables)",
            ),
            ToolParameter(
                "destination_index",
                "integer",
                "Character index where the cloned table should be inserted",
            ),
        ],
        tags=["docs", "table", "clone", "copy", "duplicate", "insert"],
        fn=clone_table,
    )
