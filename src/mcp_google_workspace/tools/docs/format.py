"""Paragraph styling and structural formatting for Google Docs."""

from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import Context

from ...registry import ToolParameter, ToolRegistry
from ._utils import pt, safe_batch_update, validate_document_id, validate_uri

VALID_NAMED_STYLES = [
    "NORMAL_TEXT",
    "TITLE",
    "SUBTITLE",
    "HEADING_1",
    "HEADING_2",
    "HEADING_3",
    "HEADING_4",
    "HEADING_5",
    "HEADING_6",
]

VALID_ALIGNMENTS = ["START", "CENTER", "END", "JUSTIFIED"]

VALID_BULLET_PRESETS = [
    "BULLET_DISC_CIRCLE_SQUARE",
    "BULLET_DIAMONDX_ARROW3D_SQUARE",
    "BULLET_CHECKBOX",
    "BULLET_ARROW_DIAMOND_DISC",
    "BULLET_STAR_CIRCLE_SQUARE",
    "BULLET_ARROW3D_CIRCLE_SQUARE",
    "BULLET_LEFTTRIANGLE_DIAMOND_DISC",
    "BULLET_DIAMONDX_HOLLOWDIAMOND_SQUARE",
    "BULLET_DIAMOND_CIRCLE_SQUARE",
    "NUMBERED_DECIMAL_ALPHA_ROMAN",
    "NUMBERED_DECIMAL_ALPHA_ROMAN_PARENS",
    "NUMBERED_DECIMAL_NESTED",
    "NUMBERED_UPPERALPHA_ALPHA_ROMAN",
    "NUMBERED_UPPERROMAN_UPPERALPHA_DECIMAL",
    "NUMBERED_ZERODECIMAL_ALPHA_ROMAN",
]


# Google Docs API limits
MAX_TABLE_ROWS = 100
MAX_TABLE_COLUMNS = 26

# Styling bounds (in PT)
MAX_WEIGHT_PT = 50
MAX_MARGIN_PT = 720  # 10 inches
MAX_PAGE_DIMENSION_PT = 2000  # ~27.8 inches

# Default horizontal rule styling (in PT)
HR_PADDING_PT = 3
HR_SPACE_PT = 6


def update_paragraph_style(
    document_id: str,
    start_index: int,
    end_index: int,
    named_style: Optional[str] = None,
    alignment: Optional[str] = None,
    line_spacing: Optional[float] = None,
    space_above: Optional[float] = None,
    space_below: Optional[float] = None,
    indent_first_line: Optional[float] = None,
    indent_start: Optional[float] = None,
    indent_end: Optional[float] = None,
    keep_with_next: Optional[bool] = None,
    keep_lines_together: Optional[bool] = None,
    segment_id: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Update paragraph-level formatting within a range.

    The range should cover at least the newline character of
    each target paragraph.
    """
    if err := validate_document_id(document_id):
        return err
    if start_index >= end_index:
        return {"error": "start_index must be less than end_index"}

    if line_spacing is not None and line_spacing <= 0:
        return {"error": "line_spacing must be positive"}
    for _name, _val in [
        ("space_above", space_above),
        ("space_below", space_below),
        ("indent_first_line", indent_first_line),
        ("indent_start", indent_start),
        ("indent_end", indent_end),
    ]:
        if _val is not None and _val < 0:
            return {"error": f"{_name} must be non-negative"}

    style: Dict[str, Any] = {}
    fields: List[str] = []

    if named_style is not None:
        upper = named_style.upper()
        if upper not in VALID_NAMED_STYLES:
            return {
                "error": (
                    f"Invalid named_style '{named_style}'. "
                    f"Must be one of: {', '.join(VALID_NAMED_STYLES)}"
                )
            }
        style["namedStyleType"] = upper
        fields.append("namedStyleType")

    if alignment is not None:
        upper = alignment.upper()
        if upper not in VALID_ALIGNMENTS:
            return {
                "error": (
                    f"Invalid alignment '{alignment}'. "
                    f"Must be one of: {', '.join(VALID_ALIGNMENTS)}"
                )
            }
        style["alignment"] = upper
        fields.append("alignment")

    if line_spacing is not None:
        style["lineSpacing"] = line_spacing
        fields.append("lineSpacing")

    if space_above is not None:
        style["spaceAbove"] = pt(space_above)
        fields.append("spaceAbove")

    if space_below is not None:
        style["spaceBelow"] = pt(space_below)
        fields.append("spaceBelow")

    if indent_first_line is not None:
        style["indentFirstLine"] = pt(indent_first_line)
        fields.append("indentFirstLine")

    if indent_start is not None:
        style["indentStart"] = pt(indent_start)
        fields.append("indentStart")

    if indent_end is not None:
        style["indentEnd"] = pt(indent_end)
        fields.append("indentEnd")

    if keep_with_next is not None:
        style["keepWithNext"] = keep_with_next
        fields.append("keepWithNext")

    if keep_lines_together is not None:
        style["keepLinesTogether"] = keep_lines_together
        fields.append("keepLinesTogether")

    if not fields:
        return {"error": "At least one paragraph style option must be provided"}

    docs_service = ctx.request_context.lifespan_context.docs_service

    range_obj: Dict[str, Any] = {
        "startIndex": start_index,
        "endIndex": end_index,
    }
    if segment_id:
        range_obj["segmentId"] = segment_id

    requests = [
        {
            "updateParagraphStyle": {
                "range": range_obj,
                "paragraphStyle": style,
                "fields": ",".join(fields),
            }
        }
    ]

    result = safe_batch_update(docs_service, document_id, requests)
    if "error" in result:
        return result

    return {
        "documentId": document_id,
        "styledRange": {"startIndex": start_index, "endIndex": end_index},
        "segmentId": segment_id,
        "appliedStyles": fields,
        "replies": result.get("replies", []),
    }


def insert_horizontal_rule(
    document_id: str,
    index: int = 1,
    weight: float = 1.0,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Insert a horizontal rule at the specified position.

    Creates a thin paragraph with a bottom border to produce
    a clean horizontal line.  The caller must ensure ``index``
    falls at a paragraph boundary (right after a newline).
    """
    if err := validate_document_id(document_id):
        return err
    if weight <= 0 or weight > MAX_WEIGHT_PT:
        return {"error": f"weight must be between 0 and {MAX_WEIGHT_PT} PT"}

    docs_service = ctx.request_context.lifespan_context.docs_service

    # Insert a newline, then style it as a border-bottom paragraph.
    # Requests execute in order; indices shift after insertText,
    # so the new paragraph occupies [index, index+1).
    requests = [
        {
            "insertText": {
                "location": {"index": index},
                "text": "\n",
            }
        },
        {
            "updateParagraphStyle": {
                "range": {"startIndex": index, "endIndex": index + 1},
                "paragraphStyle": {
                    "borderBottom": {
                        "color": {
                            "color": {"rgbColor": {"red": 0, "green": 0, "blue": 0}}
                        },
                        "width": pt(weight),
                        "padding": pt(HR_PADDING_PT),
                        "dashStyle": "SOLID",
                    },
                    "spaceAbove": pt(HR_SPACE_PT),
                    "spaceBelow": pt(HR_SPACE_PT),
                },
                "fields": "borderBottom,spaceAbove,spaceBelow",
            }
        },
    ]

    result = safe_batch_update(docs_service, document_id, requests)
    if "error" in result:
        return result

    return {
        "documentId": document_id,
        "insertedAt": index,
        "replies": result.get("replies", []),
    }


def insert_page_break(
    document_id: str,
    index: int = 1,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Insert a page break at the specified position.

    The index must be inside an existing paragraph body
    (not inside a table, header, or footer).
    """
    if err := validate_document_id(document_id):
        return err

    docs_service = ctx.request_context.lifespan_context.docs_service

    requests = [
        {
            "insertPageBreak": {
                "location": {"index": index},
            }
        }
    ]

    result = safe_batch_update(docs_service, document_id, requests)
    if "error" in result:
        return result

    return {
        "documentId": document_id,
        "insertedAt": index,
        "replies": result.get("replies", []),
    }


def insert_table(
    document_id: str,
    rows: int,
    columns: int,
    index: int = 1,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Insert an empty table at the specified position."""
    if err := validate_document_id(document_id):
        return err

    if rows < 1 or columns < 1:
        return {"error": "rows and columns must be at least 1"}
    if rows > MAX_TABLE_ROWS or columns > MAX_TABLE_COLUMNS:
        return {
            "error": f"Maximum {MAX_TABLE_ROWS} rows and {MAX_TABLE_COLUMNS} columns"
        }

    docs_service = ctx.request_context.lifespan_context.docs_service

    requests = [
        {
            "insertTable": {
                "rows": rows,
                "columns": columns,
                "location": {"index": index},
            }
        }
    ]

    result = safe_batch_update(docs_service, document_id, requests)
    if "error" in result:
        return result

    return {
        "documentId": document_id,
        "insertedAt": index,
        "rows": rows,
        "columns": columns,
        "replies": result.get("replies", []),
    }


def create_paragraph_bullets(
    document_id: str,
    start_index: int,
    end_index: int,
    bullet_preset: str = "BULLET_DISC_CIRCLE_SQUARE",
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Apply bullet or numbered list formatting to paragraphs in a range.

    Use a BULLET_* preset for unordered lists or a NUMBERED_* preset
    for ordered lists.
    """
    if err := validate_document_id(document_id):
        return err
    if start_index >= end_index:
        return {"error": "start_index must be less than end_index"}

    upper = bullet_preset.upper()
    if upper not in VALID_BULLET_PRESETS:
        return {
            "error": (
                f"Invalid bullet_preset '{bullet_preset}'. "
                f"Must be one of: {', '.join(VALID_BULLET_PRESETS)}"
            )
        }

    docs_service = ctx.request_context.lifespan_context.docs_service

    requests = [
        {
            "createParagraphBullets": {
                "range": {
                    "startIndex": start_index,
                    "endIndex": end_index,
                },
                "bulletPreset": upper,
            }
        }
    ]

    result = safe_batch_update(docs_service, document_id, requests)
    if "error" in result:
        return result

    return {
        "documentId": document_id,
        "bulletRange": {"startIndex": start_index, "endIndex": end_index},
        "preset": upper,
        "replies": result.get("replies", []),
    }


def delete_paragraph_bullets(
    document_id: str,
    start_index: int,
    end_index: int,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Remove bullet/list formatting from paragraphs in a range."""
    if err := validate_document_id(document_id):
        return err
    if start_index >= end_index:
        return {"error": "start_index must be less than end_index"}

    docs_service = ctx.request_context.lifespan_context.docs_service

    requests = [
        {
            "deleteParagraphBullets": {
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

    return {
        "documentId": document_id,
        "clearedRange": {"startIndex": start_index, "endIndex": end_index},
        "replies": result.get("replies", []),
    }


def batch_update_document(
    document_id: str,
    requests: List[Dict[str, Any]],
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Send multiple document update requests in a single API call.

    Each element in ``requests`` must be a valid Google Docs API
    request object (e.g. insertText, updateParagraphStyle,
    updateTextStyle, insertPageBreak, etc.).

    Requests are applied atomically in order.  Use this to combine
    text insertion with formatting in one efficient call.
    """
    if err := validate_document_id(document_id):
        return err

    if not requests:
        return {"error": "requests list must not be empty"}

    for i, req in enumerate(requests):
        if not isinstance(req, dict) or not req:
            return {"error": f"Request at index {i} must be a non-empty dict"}

    docs_service = ctx.request_context.lifespan_context.docs_service

    result = safe_batch_update(docs_service, document_id, requests)
    if "error" in result:
        return result

    return {
        "documentId": document_id,
        "requestCount": len(requests),
        "replies": result.get("replies", []),
    }


VALID_SECTION_TYPES = [
    "NEXT_PAGE",
    "CONTINUOUS",
    "EVEN_PAGE",
    "ODD_PAGE",
]

PAGE_PRESETS = {
    "A4": (595.28, 841.89),  # PT
    "LETTER": (612, 792),
    "LEGAL": (612, 1008),
    "A3": (841.89, 1190.55),
    "A5": (419.53, 595.28),
}


def update_document_style(
    document_id: str,
    margin_top: Optional[float] = None,
    margin_bottom: Optional[float] = None,
    margin_left: Optional[float] = None,
    margin_right: Optional[float] = None,
    page_width: Optional[float] = None,
    page_height: Optional[float] = None,
    page_preset: Optional[str] = None,
    landscape: Optional[bool] = None,
    page_number_start: Optional[int] = None,
    use_first_page_header_footer: Optional[bool] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Update document-wide style: margins, page size, orientation.

    Dimensions are in points (1 inch = 72 PT).
    Use ``page_preset`` for common sizes (A4, LETTER, LEGAL, A3, A5)
    or set ``page_width`` / ``page_height`` manually.
    """
    if err := validate_document_id(document_id):
        return err

    for _name, _val in [
        ("margin_top", margin_top),
        ("margin_bottom", margin_bottom),
        ("margin_left", margin_left),
        ("margin_right", margin_right),
    ]:
        if _val is not None and (_val < 0 or _val > MAX_MARGIN_PT):
            return {"error": f"{_name} must be between 0 and {MAX_MARGIN_PT} PT"}

    if page_width is not None and (
        page_width <= 0 or page_width > MAX_PAGE_DIMENSION_PT
    ):
        return {"error": f"page_width must be between 0 and {MAX_PAGE_DIMENSION_PT} PT"}
    if page_height is not None and (
        page_height <= 0 or page_height > MAX_PAGE_DIMENSION_PT
    ):
        return {
            "error": f"page_height must be between 0 and {MAX_PAGE_DIMENSION_PT} PT"
        }

    style: Dict[str, Any] = {}
    fields: List[str] = []

    if margin_top is not None:
        style["marginTop"] = pt(margin_top)
        fields.append("marginTop")
    if margin_bottom is not None:
        style["marginBottom"] = pt(margin_bottom)
        fields.append("marginBottom")
    if margin_left is not None:
        style["marginLeft"] = pt(margin_left)
        fields.append("marginLeft")
    if margin_right is not None:
        style["marginRight"] = pt(margin_right)
        fields.append("marginRight")

    if page_preset is not None:
        upper = page_preset.upper()
        if upper not in PAGE_PRESETS:
            return {
                "error": (
                    f"Invalid page_preset '{page_preset}'. "
                    f"Must be one of: {', '.join(PAGE_PRESETS)}"
                )
            }
        w, h = PAGE_PRESETS[upper]
        style["pageSize"] = {
            "width": pt(w),
            "height": pt(h),
        }
        fields.append("pageSize")
    elif page_width is not None or page_height is not None:
        size: Dict[str, Any] = {}
        if page_width is not None:
            size["width"] = pt(page_width)
        if page_height is not None:
            size["height"] = pt(page_height)
        style["pageSize"] = size
        fields.append("pageSize")

    if landscape is not None:
        style["flipPageOrientation"] = landscape
        fields.append("flipPageOrientation")

    if page_number_start is not None:
        style["pageNumberStart"] = page_number_start
        fields.append("pageNumberStart")

    if use_first_page_header_footer is not None:
        style["useFirstPageHeaderFooter"] = use_first_page_header_footer
        fields.append("useFirstPageHeaderFooter")

    if not fields:
        return {"error": "At least one document style option must be provided"}

    docs_service = ctx.request_context.lifespan_context.docs_service

    requests = [
        {
            "updateDocumentStyle": {
                "documentStyle": style,
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


def insert_section_break(
    document_id: str,
    index: int = 1,
    section_type: str = "NEXT_PAGE",
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Insert a section break at the specified position.

    Section breaks allow different page formatting
    (margins, orientation, headers) per section.
    """
    if err := validate_document_id(document_id):
        return err

    upper = section_type.upper()
    if upper not in VALID_SECTION_TYPES:
        return {
            "error": (
                f"Invalid section_type '{section_type}'. "
                f"Must be one of: {', '.join(VALID_SECTION_TYPES)}"
            )
        }

    docs_service = ctx.request_context.lifespan_context.docs_service

    requests = [
        {
            "insertSectionBreak": {
                "sectionType": f"SECTION_TYPE_{upper}",
                "location": {"index": index},
            }
        }
    ]

    result = safe_batch_update(docs_service, document_id, requests)
    if "error" in result:
        return result

    return {
        "documentId": document_id,
        "insertedAt": index,
        "sectionType": upper,
        "replies": result.get("replies", []),
    }


def insert_inline_image(
    document_id: str,
    uri: str,
    index: int = 1,
    width: Optional[float] = None,
    height: Optional[float] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Insert an image from a URL at the specified position.

    Width and height are in points (72 PT = 1 inch).
    If only one dimension is given, the image scales proportionally.
    """
    if err := validate_document_id(document_id):
        return err
    if err := validate_uri(uri):
        return err
    if width is not None and width <= 0:
        return {"error": "width must be positive"}
    if height is not None and height <= 0:
        return {"error": "height must be positive"}

    docs_service = ctx.request_context.lifespan_context.docs_service

    request: Dict[str, Any] = {
        "insertInlineImage": {
            "location": {"index": index},
            "uri": uri,
        }
    }

    if width is not None or height is not None:
        size: Dict[str, Any] = {}
        if width is not None:
            size["width"] = pt(width)
        if height is not None:
            size["height"] = pt(height)
        request["insertInlineImage"]["objectSize"] = size

    result = safe_batch_update(docs_service, document_id, [request])
    if "error" in result:
        return result

    return {
        "documentId": document_id,
        "insertedAt": index,
        "uri": uri,
        "replies": result.get("replies", []),
    }


def create_footnote(
    document_id: str,
    index: int = 1,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Create a footnote at the specified position.

    After creation, use insert_text with the footnote's content
    index to add text to it.
    """
    if err := validate_document_id(document_id):
        return err

    docs_service = ctx.request_context.lifespan_context.docs_service

    requests = [
        {
            "createFootnote": {
                "location": {"index": index},
            }
        }
    ]

    result = safe_batch_update(docs_service, document_id, requests)
    if "error" in result:
        return result

    footnote_id = None
    for reply in result.get("replies", []):
        fn_reply = reply.get("createFootnote", {})
        footnote_id = fn_reply.get("footnoteId")

    return {
        "documentId": document_id,
        "insertedAt": index,
        "footnoteId": footnote_id,
        "replies": result.get("replies", []),
    }


VALID_COLUMN_SEPARATOR_STYLES = ["NONE", "BETWEEN_EACH_COLUMN"]
VALID_CONTENT_DIRECTIONS = ["LEFT_TO_RIGHT", "RIGHT_TO_LEFT"]
VALID_IMAGE_REPLACE_METHODS = ["CENTER_CROP"]


def replace_image(
    document_id: str,
    image_object_id: str,
    uri: str,
    image_replace_method: str = "CENTER_CROP",
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Replace an existing image in the document with a new one.

    ``image_object_id`` can be found in the document structure
    returned by ``get_document``.
    """
    if err := validate_document_id(document_id):
        return err
    if not image_object_id or not image_object_id.strip():
        return {"error": "image_object_id must be a non-empty string"}
    if err := validate_uri(uri):
        return err

    upper_method = image_replace_method.upper()
    if upper_method not in VALID_IMAGE_REPLACE_METHODS:
        return {
            "error": (
                f"Invalid image_replace_method '{image_replace_method}'. "
                f"Must be one of: {', '.join(VALID_IMAGE_REPLACE_METHODS)}"
            )
        }

    docs_service = ctx.request_context.lifespan_context.docs_service

    requests = [
        {
            "replaceImage": {
                "imageObjectId": image_object_id,
                "uri": uri,
                "imageReplaceMethod": upper_method,
            }
        }
    ]

    result = safe_batch_update(docs_service, document_id, requests)
    if "error" in result:
        return result

    return {
        "documentId": document_id,
        "replacedImageId": image_object_id,
        "newUri": uri,
        "replies": result.get("replies", []),
    }


def delete_positioned_object(
    document_id: str,
    object_id: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Delete a positioned (floating) object from the document.

    Positioned objects include floating images and other anchored
    elements.  Use ``get_document`` to find object IDs in the
    ``positionedObjects`` field.
    """
    if err := validate_document_id(document_id):
        return err
    if not object_id or not object_id.strip():
        return {"error": "object_id must be a non-empty string"}

    docs_service = ctx.request_context.lifespan_context.docs_service

    requests = [
        {
            "deletePositionedObject": {
                "objectId": object_id,
            }
        }
    ]

    result = safe_batch_update(docs_service, document_id, requests)
    if "error" in result:
        return result

    return {
        "documentId": document_id,
        "deletedObjectId": object_id,
        "replies": result.get("replies", []),
    }


def update_section_style(
    document_id: str,
    start_index: int,
    end_index: int,
    column_separator_style: Optional[str] = None,
    content_direction: Optional[str] = None,
    margin_top: Optional[float] = None,
    margin_bottom: Optional[float] = None,
    margin_left: Optional[float] = None,
    margin_right: Optional[float] = None,
    margin_header: Optional[float] = None,
    margin_footer: Optional[float] = None,
    page_number_start: Optional[int] = None,
    use_first_page_header_footer: Optional[bool] = None,
    flip_page_orientation: Optional[bool] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Update section-level style within a range.

    Sections can have different margins, orientation, and column
    layout.  The range must cover at least one section break or
    the entire document body for the default section.
    """
    if err := validate_document_id(document_id):
        return err
    if start_index >= end_index:
        return {"error": "start_index must be less than end_index"}

    for _name, _val in [
        ("margin_top", margin_top),
        ("margin_bottom", margin_bottom),
        ("margin_left", margin_left),
        ("margin_right", margin_right),
        ("margin_header", margin_header),
        ("margin_footer", margin_footer),
    ]:
        if _val is not None and (_val < 0 or _val > MAX_MARGIN_PT):
            return {"error": f"{_name} must be between 0 and {MAX_MARGIN_PT} PT"}

    style: Dict[str, Any] = {}
    fields: List[str] = []

    if column_separator_style is not None:
        upper = column_separator_style.upper()
        if upper not in VALID_COLUMN_SEPARATOR_STYLES:
            return {
                "error": (
                    f"Invalid column_separator_style '{column_separator_style}'. "
                    f"Must be one of: {', '.join(VALID_COLUMN_SEPARATOR_STYLES)}"
                )
            }
        style["columnSeparatorStyle"] = upper
        fields.append("columnSeparatorStyle")

    if content_direction is not None:
        upper = content_direction.upper()
        if upper not in VALID_CONTENT_DIRECTIONS:
            return {
                "error": (
                    f"Invalid content_direction '{content_direction}'. "
                    f"Must be one of: {', '.join(VALID_CONTENT_DIRECTIONS)}"
                )
            }
        style["contentDirection"] = upper
        fields.append("contentDirection")

    for name, value in [
        ("marginTop", margin_top),
        ("marginBottom", margin_bottom),
        ("marginLeft", margin_left),
        ("marginRight", margin_right),
        ("marginHeader", margin_header),
        ("marginFooter", margin_footer),
    ]:
        if value is not None:
            style[name] = pt(value)
            fields.append(name)

    if page_number_start is not None:
        if page_number_start < 0:
            return {"error": "page_number_start must be non-negative"}
        style["pageNumberStart"] = page_number_start
        fields.append("pageNumberStart")

    if use_first_page_header_footer is not None:
        style["useFirstPageHeaderFooter"] = use_first_page_header_footer
        fields.append("useFirstPageHeaderFooter")

    if flip_page_orientation is not None:
        style["flipPageOrientation"] = flip_page_orientation
        fields.append("flipPageOrientation")

    if not fields:
        return {"error": "At least one section style option must be provided"}

    docs_service = ctx.request_context.lifespan_context.docs_service

    requests = [
        {
            "updateSectionStyle": {
                "range": {
                    "startIndex": start_index,
                    "endIndex": end_index,
                },
                "sectionStyle": style,
                "fields": ",".join(fields),
            }
        }
    ]

    result = safe_batch_update(docs_service, document_id, requests)
    if "error" in result:
        return result

    return {
        "documentId": document_id,
        "styledRange": {"startIndex": start_index, "endIndex": end_index},
        "appliedStyles": fields,
        "replies": result.get("replies", []),
    }


def update_named_style(
    document_id: str,
    named_style_type: str,
    bold: Optional[bool] = None,
    italic: Optional[bool] = None,
    underline: Optional[bool] = None,
    font_size: Optional[float] = None,
    font_family: Optional[str] = None,
    foreground_color: Optional[Dict[str, float]] = None,
    alignment: Optional[str] = None,
    line_spacing: Optional[float] = None,
    space_above: Optional[float] = None,
    space_below: Optional[float] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Update a named style definition (e.g. HEADING_1, NORMAL_TEXT).

    Changes the default styling for all paragraphs using that
    named style across the entire document.
    """
    if err := validate_document_id(document_id):
        return err

    upper_type = named_style_type.upper()
    if upper_type not in VALID_NAMED_STYLES:
        return {
            "error": (
                f"Invalid named_style_type '{named_style_type}'. "
                f"Must be one of: {', '.join(VALID_NAMED_STYLES)}"
            )
        }

    text_style: Dict[str, Any] = {}
    text_fields: List[str] = []
    paragraph_style: Dict[str, Any] = {}
    paragraph_fields: List[str] = []

    if bold is not None:
        text_style["bold"] = bold
        text_fields.append("bold")
    if italic is not None:
        text_style["italic"] = italic
        text_fields.append("italic")
    if underline is not None:
        text_style["underline"] = underline
        text_fields.append("underline")
    if font_size is not None:
        if font_size <= 0:
            return {"error": "font_size must be positive"}
        text_style["fontSize"] = pt(font_size)
        text_fields.append("fontSize")
    if font_family is not None:
        text_style["weightedFontFamily"] = {"fontFamily": font_family}
        text_fields.append("weightedFontFamily")
    if foreground_color is not None:
        text_style["foregroundColor"] = {"color": {"rgbColor": foreground_color}}
        text_fields.append("foregroundColor")

    if alignment is not None:
        upper = alignment.upper()
        if upper not in VALID_ALIGNMENTS:
            return {
                "error": (
                    f"Invalid alignment '{alignment}'. "
                    f"Must be one of: {', '.join(VALID_ALIGNMENTS)}"
                )
            }
        paragraph_style["alignment"] = upper
        paragraph_fields.append("alignment")
    if line_spacing is not None:
        if line_spacing <= 0:
            return {"error": "line_spacing must be positive"}
        paragraph_style["lineSpacing"] = line_spacing
        paragraph_fields.append("lineSpacing")
    if space_above is not None:
        if space_above < 0:
            return {"error": "space_above must be non-negative"}
        paragraph_style["spaceAbove"] = pt(space_above)
        paragraph_fields.append("spaceAbove")
    if space_below is not None:
        if space_below < 0:
            return {"error": "space_below must be non-negative"}
        paragraph_style["spaceBelow"] = pt(space_below)
        paragraph_fields.append("spaceBelow")

    if not text_fields and not paragraph_fields:
        return {"error": "At least one style option must be provided"}

    named_style_obj: Dict[str, Any] = {"namedStyleType": upper_type}
    all_fields: List[str] = ["namedStyleType"]

    if text_style:
        named_style_obj["textStyle"] = text_style
        all_fields.extend(f"textStyle.{f}" for f in text_fields)
    if paragraph_style:
        named_style_obj["paragraphStyle"] = paragraph_style
        all_fields.extend(f"paragraphStyle.{f}" for f in paragraph_fields)

    docs_service = ctx.request_context.lifespan_context.docs_service

    requests = [
        {
            "updateNamedStyle": {
                "namedStyle": named_style_obj,
                "fields": ",".join(all_fields),
            }
        }
    ]

    result = safe_batch_update(docs_service, document_id, requests)
    if "error" in result:
        return result

    return {
        "documentId": document_id,
        "namedStyleType": upper_type,
        "appliedStyles": all_fields,
        "replies": result.get("replies", []),
    }


def register(registry: ToolRegistry) -> None:
    """Register all Docs formatting tools in the registry."""
    registry.register(
        name="update_paragraph_style",
        description=(
            "Update paragraph-level formatting: heading level "
            "(TITLE, HEADING_1-6), alignment (START/CENTER/END/JUSTIFIED), "
            "line spacing, space above/below, and indentation."
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
                "Start character index of paragraphs to style",
            ),
            ToolParameter(
                "end_index",
                "integer",
                "End character index of paragraphs to style (exclusive)",
            ),
            ToolParameter(
                "named_style",
                "string",
                "Paragraph style: NORMAL_TEXT, TITLE, SUBTITLE, "
                "HEADING_1 through HEADING_6",
                required=False,
            ),
            ToolParameter(
                "alignment",
                "string",
                "Text alignment: START, CENTER, END, or JUSTIFIED",
                required=False,
            ),
            ToolParameter(
                "line_spacing",
                "number",
                "Line spacing as percentage (100=single, 150=1.5, 200=double)",
                required=False,
            ),
            ToolParameter(
                "space_above",
                "number",
                "Space above paragraph in points",
                required=False,
            ),
            ToolParameter(
                "space_below",
                "number",
                "Space below paragraph in points",
                required=False,
            ),
            ToolParameter(
                "indent_first_line",
                "number",
                "First line indent in points",
                required=False,
            ),
            ToolParameter(
                "indent_start",
                "number",
                "Left indent in points",
                required=False,
            ),
            ToolParameter(
                "indent_end",
                "number",
                "Right indent in points",
                required=False,
            ),
            ToolParameter(
                "keep_with_next",
                "boolean",
                "Keep paragraph with next (prevent page break between)",
                required=False,
            ),
            ToolParameter(
                "keep_lines_together",
                "boolean",
                "Keep all lines of paragraph on same page",
                required=False,
            ),
            ToolParameter(
                "segment_id",
                "string",
                "Segment ID for styling paragraphs inside a header or footer. "
                "Use the ID returned by create_header/create_footer. "
                "Omit to style body paragraphs.",
                required=False,
            ),
        ],
        tags=[
            "docs",
            "format",
            "paragraph",
            "heading",
            "alignment",
            "spacing",
            "indent",
            "style",
        ],
        fn=update_paragraph_style,
    )

    registry.register(
        name="insert_horizontal_rule",
        description=(
            "Insert a horizontal rule (line separator) at a position. "
            "Creates a clean border line between sections."
        ),
        parameters=[
            ToolParameter(
                "document_id",
                "string",
                "The ID of the document (from URL)",
            ),
            ToolParameter(
                "index",
                "integer",
                "Character index to insert at (1 = start of body, default: 1)",
                required=False,
                default=1,
            ),
            ToolParameter(
                "weight",
                "number",
                "Line thickness in points (default: 1.0)",
                required=False,
                default=1.0,
            ),
        ],
        tags=["docs", "format", "horizontal", "rule", "line", "separator", "divider"],
        fn=insert_horizontal_rule,
    )

    registry.register(
        name="insert_page_break",
        description=(
            "Insert a page break at a position in the document. "
            "Must be inside a paragraph body, not a table or header."
        ),
        parameters=[
            ToolParameter(
                "document_id",
                "string",
                "The ID of the document (from URL)",
            ),
            ToolParameter(
                "index",
                "integer",
                "Character index to insert page break (1 = start, default: 1)",
                required=False,
                default=1,
            ),
        ],
        tags=["docs", "format", "page", "break", "section", "newpage"],
        fn=insert_page_break,
    )

    registry.register(
        name="insert_table",
        description=(
            "Insert an empty table with specified rows and columns "
            "at a position in the document."
        ),
        parameters=[
            ToolParameter(
                "document_id",
                "string",
                "The ID of the document (from URL)",
            ),
            ToolParameter(
                "rows",
                "integer",
                "Number of rows (1-100)",
            ),
            ToolParameter(
                "columns",
                "integer",
                "Number of columns (1-26)",
            ),
            ToolParameter(
                "index",
                "integer",
                "Character index to insert table (1 = start, default: 1)",
                required=False,
                default=1,
            ),
        ],
        tags=["docs", "format", "table", "insert", "grid", "create"],
        fn=insert_table,
    )

    registry.register(
        name="create_paragraph_bullets",
        description=(
            "Apply bullet or numbered list formatting to paragraphs. "
            "Use BULLET_* presets for unordered lists, "
            "NUMBERED_* presets for ordered lists."
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
                "Start character index of paragraphs to format",
            ),
            ToolParameter(
                "end_index",
                "integer",
                "End character index of paragraphs to format (exclusive)",
            ),
            ToolParameter(
                "bullet_preset",
                "string",
                "Bullet style preset (default: BULLET_DISC_CIRCLE_SQUARE). "
                "Options: BULLET_DISC_CIRCLE_SQUARE, BULLET_CHECKBOX, "
                "NUMBERED_DECIMAL_ALPHA_ROMAN, etc.",
                required=False,
                default="BULLET_DISC_CIRCLE_SQUARE",
            ),
        ],
        tags=["docs", "format", "bullets", "list", "numbered", "ordered", "unordered"],
        fn=create_paragraph_bullets,
    )

    registry.register(
        name="delete_paragraph_bullets",
        description="Remove bullet or list formatting from paragraphs in a range.",
        parameters=[
            ToolParameter(
                "document_id",
                "string",
                "The ID of the document (from URL)",
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
        tags=["docs", "format", "bullets", "list", "remove", "delete"],
        fn=delete_paragraph_bullets,
    )

    registry.register(
        name="batch_update_document",
        description=(
            "Send multiple Google Docs API requests in a single atomic call. "
            "Accepts raw request objects (insertText, updateParagraphStyle, "
            "updateTextStyle, insertPageBreak, insertTable, etc.). "
            "Use this for efficient multi-step document construction."
        ),
        parameters=[
            ToolParameter(
                "document_id",
                "string",
                "The ID of the document (from URL)",
            ),
            ToolParameter(
                "requests",
                "array",
                "List of Google Docs API request objects. "
                "Each is a dict with one key (the request type) "
                "e.g. [{'insertText': {...}}, {'updateParagraphStyle': {...}}]",
            ),
        ],
        tags=[
            "docs",
            "batch",
            "update",
            "multiple",
            "requests",
            "atomic",
            "efficient",
        ],
        fn=batch_update_document,
    )

    registry.register(
        name="update_document_style",
        description=(
            "Update document-wide style: page margins (in PT), "
            "page size (A4/LETTER/LEGAL or custom), orientation, "
            "and page numbering start."
        ),
        parameters=[
            ToolParameter(
                "document_id",
                "string",
                "The ID of the document (from URL)",
            ),
            ToolParameter(
                "margin_top",
                "number",
                "Top margin in points (72 PT = 1 inch)",
                required=False,
            ),
            ToolParameter(
                "margin_bottom",
                "number",
                "Bottom margin in points",
                required=False,
            ),
            ToolParameter(
                "margin_left",
                "number",
                "Left margin in points",
                required=False,
            ),
            ToolParameter(
                "margin_right",
                "number",
                "Right margin in points",
                required=False,
            ),
            ToolParameter(
                "page_preset",
                "string",
                "Page size preset: A4, LETTER, LEGAL, A3, A5",
                required=False,
            ),
            ToolParameter(
                "page_width",
                "number",
                "Custom page width in points (ignored if page_preset set)",
                required=False,
            ),
            ToolParameter(
                "page_height",
                "number",
                "Custom page height in points (ignored if page_preset set)",
                required=False,
            ),
            ToolParameter(
                "landscape",
                "boolean",
                "Flip to landscape orientation",
                required=False,
            ),
            ToolParameter(
                "page_number_start",
                "integer",
                "Starting page number",
                required=False,
            ),
            ToolParameter(
                "use_first_page_header_footer",
                "boolean",
                "Use different header/footer on first page",
                required=False,
            ),
        ],
        tags=[
            "docs",
            "format",
            "document",
            "style",
            "margins",
            "page",
            "size",
            "orientation",
        ],
        fn=update_document_style,
    )

    registry.register(
        name="insert_section_break",
        description=(
            "Insert a section break for different formatting per section "
            "(margins, orientation, headers). Types: NEXT_PAGE, "
            "CONTINUOUS, EVEN_PAGE, ODD_PAGE."
        ),
        parameters=[
            ToolParameter(
                "document_id",
                "string",
                "The ID of the document (from URL)",
            ),
            ToolParameter(
                "index",
                "integer",
                "Character index to insert at (1 = start, default: 1)",
                required=False,
                default=1,
            ),
            ToolParameter(
                "section_type",
                "string",
                "Break type: NEXT_PAGE, CONTINUOUS, EVEN_PAGE, ODD_PAGE "
                "(default: NEXT_PAGE)",
                required=False,
                default="NEXT_PAGE",
            ),
        ],
        tags=["docs", "format", "section", "break", "page", "layout"],
        fn=insert_section_break,
    )

    registry.register(
        name="insert_inline_image",
        description=(
            "Insert an image from an HTTPS URL at a position. "
            "Optionally specify width/height in points (72 PT = 1 inch)."
        ),
        parameters=[
            ToolParameter(
                "document_id",
                "string",
                "The ID of the document (from URL)",
            ),
            ToolParameter(
                "uri",
                "string",
                "HTTPS URL of the image to insert",
            ),
            ToolParameter(
                "index",
                "integer",
                "Character index to insert at (1 = start, default: 1)",
                required=False,
                default=1,
            ),
            ToolParameter(
                "width",
                "number",
                "Image width in points (72 PT = 1 inch)",
                required=False,
            ),
            ToolParameter(
                "height",
                "number",
                "Image height in points",
                required=False,
            ),
        ],
        tags=["docs", "insert", "image", "inline", "picture", "logo"],
        fn=insert_inline_image,
    )

    registry.register(
        name="create_footnote",
        description=(
            "Create a footnote at a position. Returns the footnote ID. "
            "Use insert_text with the footnote content index to add text."
        ),
        parameters=[
            ToolParameter(
                "document_id",
                "string",
                "The ID of the document (from URL)",
            ),
            ToolParameter(
                "index",
                "integer",
                "Character index to place footnote anchor (1 = start, default: 1)",
                required=False,
                default=1,
            ),
        ],
        tags=["docs", "footnote", "note", "reference", "annotation"],
        fn=create_footnote,
    )

    registry.register(
        name="replace_image",
        description=(
            "Replace an existing image in the document with a new one "
            "from an HTTPS URL. Use get_document to find image object IDs."
        ),
        parameters=[
            ToolParameter(
                "document_id",
                "string",
                "The ID of the document (from URL)",
            ),
            ToolParameter(
                "image_object_id",
                "string",
                "The object ID of the image to replace (from get_document)",
            ),
            ToolParameter(
                "uri",
                "string",
                "HTTPS URL of the new image",
            ),
            ToolParameter(
                "image_replace_method",
                "string",
                "How to replace: CENTER_CROP (default: CENTER_CROP)",
                required=False,
                default="CENTER_CROP",
            ),
        ],
        tags=["docs", "image", "replace", "update", "picture"],
        fn=replace_image,
    )

    registry.register(
        name="delete_positioned_object",
        description=(
            "Delete a positioned (floating) object from the document. "
            "Use get_document to find object IDs in positionedObjects."
        ),
        parameters=[
            ToolParameter(
                "document_id",
                "string",
                "The ID of the document (from URL)",
            ),
            ToolParameter(
                "object_id",
                "string",
                "The positioned object ID to delete",
            ),
        ],
        tags=["docs", "delete", "positioned", "object", "floating", "image"],
        fn=delete_positioned_object,
    )

    registry.register(
        name="update_section_style",
        description=(
            "Update section-level style: margins, orientation, "
            "column separator, content direction, and page numbering. "
            "Use insert_section_break to create sections first."
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
                "Start character index of the section range",
            ),
            ToolParameter(
                "end_index",
                "integer",
                "End character index of the section range (exclusive)",
            ),
            ToolParameter(
                "column_separator_style",
                "string",
                "Column separator: NONE or BETWEEN_EACH_COLUMN",
                required=False,
            ),
            ToolParameter(
                "content_direction",
                "string",
                "Text direction: LEFT_TO_RIGHT or RIGHT_TO_LEFT",
                required=False,
            ),
            ToolParameter(
                "margin_top",
                "number",
                "Section top margin in points",
                required=False,
            ),
            ToolParameter(
                "margin_bottom",
                "number",
                "Section bottom margin in points",
                required=False,
            ),
            ToolParameter(
                "margin_left",
                "number",
                "Section left margin in points",
                required=False,
            ),
            ToolParameter(
                "margin_right",
                "number",
                "Section right margin in points",
                required=False,
            ),
            ToolParameter(
                "margin_header",
                "number",
                "Distance from top of page to header in points",
                required=False,
            ),
            ToolParameter(
                "margin_footer",
                "number",
                "Distance from bottom of page to footer in points",
                required=False,
            ),
            ToolParameter(
                "page_number_start",
                "integer",
                "Starting page number for this section",
                required=False,
            ),
            ToolParameter(
                "use_first_page_header_footer",
                "boolean",
                "Use different header/footer on first page of section",
                required=False,
            ),
            ToolParameter(
                "flip_page_orientation",
                "boolean",
                "Flip page orientation for this section",
                required=False,
            ),
        ],
        tags=[
            "docs",
            "format",
            "section",
            "style",
            "margins",
            "orientation",
            "columns",
            "direction",
        ],
        fn=update_section_style,
    )

    registry.register(
        name="update_named_style",
        description=(
            "Update a named style definition (NORMAL_TEXT, TITLE, "
            "HEADING_1-6, SUBTITLE). Changes default styling for all "
            "paragraphs using that style across the document."
        ),
        parameters=[
            ToolParameter(
                "document_id",
                "string",
                "The ID of the document (from URL)",
            ),
            ToolParameter(
                "named_style_type",
                "string",
                "Style to update: NORMAL_TEXT, TITLE, SUBTITLE, "
                "HEADING_1 through HEADING_6",
            ),
            ToolParameter(
                "bold",
                "boolean",
                "Set bold for the named style",
                required=False,
            ),
            ToolParameter(
                "italic",
                "boolean",
                "Set italic for the named style",
                required=False,
            ),
            ToolParameter(
                "underline",
                "boolean",
                "Set underline for the named style",
                required=False,
            ),
            ToolParameter(
                "font_size",
                "number",
                "Font size in points for the named style",
                required=False,
            ),
            ToolParameter(
                "font_family",
                "string",
                "Font family name (e.g. 'Arial', 'Times New Roman')",
                required=False,
            ),
            ToolParameter(
                "foreground_color",
                "object",
                "Text color as {red, green, blue} 0.0-1.0",
                required=False,
            ),
            ToolParameter(
                "alignment",
                "string",
                "Paragraph alignment: START, CENTER, END, or JUSTIFIED",
                required=False,
            ),
            ToolParameter(
                "line_spacing",
                "number",
                "Line spacing as percentage (100=single, 200=double)",
                required=False,
            ),
            ToolParameter(
                "space_above",
                "number",
                "Space above paragraph in points",
                required=False,
            ),
            ToolParameter(
                "space_below",
                "number",
                "Space below paragraph in points",
                required=False,
            ),
        ],
        tags=[
            "docs",
            "format",
            "named",
            "style",
            "heading",
            "title",
            "global",
            "theme",
        ],
        fn=update_named_style,
    )
