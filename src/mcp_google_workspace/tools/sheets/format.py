"""Formatting operations for Google Sheets.

Note on sheet ID resolution
----------------------------
Each formatting function resolves the sheet name to a numeric ID via
``get_sheet_id_or_error``, which makes one ``spreadsheets.get`` API call.
Because MCP tools are invoked independently by the LLM, there is no
shared state across calls to amortize this cost.  If batch performance
becomes a concern, consider a per-request caching layer in
``WorkspaceContext`` keyed on ``(spreadsheet_id, sheet_name)``.
"""

from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import Context

from ...registry import ToolParameter, ToolRegistry
from ...utils.sheets import SheetNotFoundError, get_sheet_id_or_error, parse_a1_notation

_MAX_PIXEL_SIZE = 10000
_MAX_FONT_SIZE = 400


def format_cells(
    spreadsheet_id: str,
    sheet: str,
    range: str,
    bold: Optional[bool] = None,
    italic: Optional[bool] = None,
    font_size: Optional[int] = None,
    font_family: Optional[str] = None,
    foreground_color: Optional[Dict[str, float]] = None,
    background_color: Optional[Dict[str, float]] = None,
    horizontal_alignment: Optional[str] = None,
    vertical_alignment: Optional[str] = None,
    wrap_strategy: Optional[str] = None,
    number_format_type: Optional[str] = None,
    number_format_pattern: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Apply formatting to a range of cells in a sheet."""
    sheets_service = ctx.request_context.lifespan_context.sheets_service
    try:
        sheet_id = get_sheet_id_or_error(sheets_service, spreadsheet_id, sheet)
    except SheetNotFoundError as e:
        return {"error": str(e)}

    try:
        range_indices = parse_a1_notation(range)
    except ValueError as e:
        return {"error": str(e)}

    cell_format: Dict[str, Any] = {}
    fields: List[str] = []

    text_format: Dict[str, Any] = {}
    if bold is not None:
        text_format["bold"] = bold
        fields.append("userEnteredFormat.textFormat.bold")
    if italic is not None:
        text_format["italic"] = italic
        fields.append("userEnteredFormat.textFormat.italic")
    if font_size is not None:
        if font_size < 1 or font_size > _MAX_FONT_SIZE:
            return {"error": f"font_size must be between 1 and {_MAX_FONT_SIZE}"}
        text_format["fontSize"] = font_size
        fields.append("userEnteredFormat.textFormat.fontSize")
    if font_family is not None:
        text_format["fontFamily"] = font_family
        fields.append("userEnteredFormat.textFormat.fontFamily")
    if foreground_color is not None:
        text_format["foregroundColorStyle"] = {"rgbColor": foreground_color}
        fields.append("userEnteredFormat.textFormat.foregroundColorStyle")
    if text_format:
        cell_format["textFormat"] = text_format

    if background_color is not None:
        cell_format["backgroundColorStyle"] = {"rgbColor": background_color}
        fields.append("userEnteredFormat.backgroundColorStyle")

    if horizontal_alignment is not None:
        valid = ["LEFT", "CENTER", "RIGHT"]
        if horizontal_alignment.upper() not in valid:
            return {"error": f"horizontal_alignment must be one of: {', '.join(valid)}"}
        cell_format["horizontalAlignment"] = horizontal_alignment.upper()
        fields.append("userEnteredFormat.horizontalAlignment")

    if vertical_alignment is not None:
        valid_va = ["TOP", "MIDDLE", "BOTTOM"]
        if vertical_alignment.upper() not in valid_va:
            return {"error": f"vertical_alignment must be one of: {', '.join(valid_va)}"}
        cell_format["verticalAlignment"] = vertical_alignment.upper()
        fields.append("userEnteredFormat.verticalAlignment")

    if wrap_strategy is not None:
        valid_ws = ["OVERFLOW_CELL", "LEGACY_WRAP", "CLIP", "WRAP"]
        if wrap_strategy.upper() not in valid_ws:
            return {"error": f"wrap_strategy must be one of: {', '.join(valid_ws)}"}
        cell_format["wrapStrategy"] = wrap_strategy.upper()
        fields.append("userEnteredFormat.wrapStrategy")

    if number_format_type is not None or number_format_pattern is not None:
        num_fmt: Dict[str, Any] = {}
        if number_format_type:
            num_fmt["type"] = number_format_type.upper()
        if number_format_pattern:
            num_fmt["pattern"] = number_format_pattern
        cell_format["numberFormat"] = num_fmt
        fields.append("userEnteredFormat.numberFormat")

    if not fields:
        return {"error": "At least one formatting option must be provided"}

    return (
        sheets_service.spreadsheets()
        .batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {
                        "repeatCell": {
                            "range": {"sheetId": sheet_id, **range_indices},
                            "cell": {"userEnteredFormat": cell_format},
                            "fields": ",".join(fields),
                        }
                    }
                ]
            },
        )
        .execute()
    )


def read_cell_format(
    spreadsheet_id: str,
    sheet: str,
    range: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Read the formatting of cells in a range."""
    sheets_service = ctx.request_context.lifespan_context.sheets_service
    full_range = f"{sheet}!{range}"

    result = (
        sheets_service.spreadsheets()
        .get(
            spreadsheetId=spreadsheet_id,
            ranges=[full_range],
            includeGridData=True,
            fields=(
                "sheets(data(rowData(values("
                "userEnteredFormat,effectiveFormat"
                "))))"
            ),
        )
        .execute()
    )

    rows = []
    for sheet_data in result.get("sheets", []):
        for data in sheet_data.get("data", []):
            for row in data.get("rowData", []):
                cells = []
                for cell in row.get("values", []):
                    fmt = cell.get("userEnteredFormat") or cell.get("effectiveFormat") or {}
                    cells.append(fmt)
                rows.append(cells)

    return {"spreadsheetId": spreadsheet_id, "range": full_range, "formats": rows}


def freeze_rows_columns(
    spreadsheet_id: str,
    sheet: str,
    frozen_rows: int = 0,
    frozen_columns: int = 0,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Freeze rows and/or columns in a sheet."""
    sheets_service = ctx.request_context.lifespan_context.sheets_service
    try:
        sheet_id = get_sheet_id_or_error(sheets_service, spreadsheet_id, sheet)
    except SheetNotFoundError as e:
        return {"error": str(e)}

    return (
        sheets_service.spreadsheets()
        .batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {
                        "updateSheetProperties": {
                            "properties": {
                                "sheetId": sheet_id,
                                "gridProperties": {
                                    "frozenRowCount": frozen_rows,
                                    "frozenColumnCount": frozen_columns,
                                },
                            },
                            "fields": (
                                "gridProperties.frozenRowCount,"
                                "gridProperties.frozenColumnCount"
                            ),
                        }
                    }
                ]
            },
        )
        .execute()
    )


def set_column_widths(
    spreadsheet_id: str,
    sheet: str,
    start_column: int,
    end_column: int,
    width: int,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Set the pixel width of a range of columns."""
    sheets_service = ctx.request_context.lifespan_context.sheets_service
    try:
        sheet_id = get_sheet_id_or_error(sheets_service, spreadsheet_id, sheet)
    except SheetNotFoundError as e:
        return {"error": str(e)}

    if start_column < 0:
        return {"error": "start_column must be >= 0"}
    if end_column <= start_column:
        return {"error": "end_column must be greater than start_column"}
    if width <= 0 or width > _MAX_PIXEL_SIZE:
        return {"error": f"width must be between 1 and {_MAX_PIXEL_SIZE}"}

    return (
        sheets_service.spreadsheets()
        .batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {
                        "updateDimensionProperties": {
                            "range": {
                                "sheetId": sheet_id,
                                "dimension": "COLUMNS",
                                "startIndex": start_column,
                                "endIndex": end_column,
                            },
                            "properties": {"pixelSize": width},
                            "fields": "pixelSize",
                        }
                    }
                ]
            },
        )
        .execute()
    )


def set_row_heights(
    spreadsheet_id: str,
    sheet: str,
    start_row: int,
    end_row: int,
    height: int,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Set the pixel height of a range of rows."""
    sheets_service = ctx.request_context.lifespan_context.sheets_service
    try:
        sheet_id = get_sheet_id_or_error(sheets_service, spreadsheet_id, sheet)
    except SheetNotFoundError as e:
        return {"error": str(e)}

    if start_row < 0:
        return {"error": "start_row must be >= 0"}
    if end_row <= start_row:
        return {"error": "end_row must be greater than start_row"}
    if height <= 0 or height > _MAX_PIXEL_SIZE:
        return {"error": f"height must be between 1 and {_MAX_PIXEL_SIZE}"}

    return (
        sheets_service.spreadsheets()
        .batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {
                        "updateDimensionProperties": {
                            "range": {
                                "sheetId": sheet_id,
                                "dimension": "ROWS",
                                "startIndex": start_row,
                                "endIndex": end_row,
                            },
                            "properties": {"pixelSize": height},
                            "fields": "pixelSize",
                        }
                    }
                ]
            },
        )
        .execute()
    )


def auto_resize_columns(
    spreadsheet_id: str,
    sheet: str,
    start_column: int = 0,
    end_column: Optional[int] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Auto-resize columns to fit their content."""
    sheets_service = ctx.request_context.lifespan_context.sheets_service
    try:
        sheet_id = get_sheet_id_or_error(sheets_service, spreadsheet_id, sheet)
    except SheetNotFoundError as e:
        return {"error": str(e)}

    dim_range: Dict[str, Any] = {
        "sheetId": sheet_id,
        "dimension": "COLUMNS",
        "startIndex": start_column,
    }
    if end_column is not None:
        dim_range["endIndex"] = end_column

    return (
        sheets_service.spreadsheets()
        .batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [{"autoResizeDimensions": {"dimensions": dim_range}}]
            },
        )
        .execute()
    )


def auto_resize_rows(
    spreadsheet_id: str,
    sheet: str,
    start_row: int = 0,
    end_row: Optional[int] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Auto-resize rows to fit their content."""
    sheets_service = ctx.request_context.lifespan_context.sheets_service
    try:
        sheet_id = get_sheet_id_or_error(sheets_service, spreadsheet_id, sheet)
    except SheetNotFoundError as e:
        return {"error": str(e)}

    dim_range: Dict[str, Any] = {
        "sheetId": sheet_id,
        "dimension": "ROWS",
        "startIndex": start_row,
    }
    if end_row is not None:
        dim_range["endIndex"] = end_row

    return (
        sheets_service.spreadsheets()
        .batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [{"autoResizeDimensions": {"dimensions": dim_range}}]
            },
        )
        .execute()
    )


def set_dropdown_validation(
    spreadsheet_id: str,
    sheet: str,
    range: str,
    values: List[str],
    strict: bool = True,
    show_dropdown: bool = True,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Create a dropdown list data validation rule for a cell range."""
    sheets_service = ctx.request_context.lifespan_context.sheets_service
    try:
        sheet_id = get_sheet_id_or_error(sheets_service, spreadsheet_id, sheet)
    except SheetNotFoundError as e:
        return {"error": str(e)}

    if not values:
        return {"error": "values must be a non-empty list"}

    try:
        range_indices = parse_a1_notation(range)
    except ValueError as e:
        return {"error": str(e)}

    condition_values = [{"userEnteredValue": str(v)} for v in values]

    return (
        sheets_service.spreadsheets()
        .batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {
                        "setDataValidation": {
                            "range": {"sheetId": sheet_id, **range_indices},
                            "rule": {
                                "condition": {
                                    "type": "ONE_OF_LIST",
                                    "values": condition_values,
                                },
                                "strict": strict,
                                "showCustomUi": show_dropdown,
                            },
                        }
                    }
                ]
            },
        )
        .execute()
    )


def protect_range(
    spreadsheet_id: str,
    sheet: str,
    range: Optional[str] = None,
    description: Optional[str] = None,
    warning_only: bool = False,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Protect a range or entire sheet from editing."""
    sheets_service = ctx.request_context.lifespan_context.sheets_service
    try:
        sheet_id = get_sheet_id_or_error(sheets_service, spreadsheet_id, sheet)
    except SheetNotFoundError as e:
        return {"error": str(e)}

    protected_range: Dict[str, Any] = {"sheetId": sheet_id}
    if range:
        try:
            range_indices = parse_a1_notation(range)
            protected_range.update(range_indices)
        except ValueError as e:
            return {"error": str(e)}

    body: Dict[str, Any] = {
        "range": protected_range,
        "warningOnly": warning_only,
    }
    if description:
        body["description"] = description

    return (
        sheets_service.spreadsheets()
        .batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"addProtectedRange": {"protectedRange": body}}]},
        )
        .execute()
    )


def add_conditional_formatting(
    spreadsheet_id: str,
    sheet: str,
    range: str,
    condition_type: str,
    condition_values: Optional[List[str]] = None,
    format_bold: Optional[bool] = None,
    format_italic: Optional[bool] = None,
    format_background_color: Optional[Dict[str, float]] = None,
    format_foreground_color: Optional[Dict[str, float]] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Add a conditional formatting rule to a range."""
    sheets_service = ctx.request_context.lifespan_context.sheets_service
    try:
        sheet_id = get_sheet_id_or_error(sheets_service, spreadsheet_id, sheet)
    except SheetNotFoundError as e:
        return {"error": str(e)}

    try:
        range_indices = parse_a1_notation(range)
    except ValueError as e:
        return {"error": str(e)}

    cell_format: Dict[str, Any] = {}
    text_format: Dict[str, Any] = {}
    if format_bold is not None:
        text_format["bold"] = format_bold
    if format_italic is not None:
        text_format["italic"] = format_italic
    if format_foreground_color is not None:
        text_format["foregroundColorStyle"] = {"rgbColor": format_foreground_color}
    if text_format:
        cell_format["textFormat"] = text_format
    if format_background_color is not None:
        cell_format["backgroundColorStyle"] = {"rgbColor": format_background_color}

    if not cell_format:
        return {"error": "At least one format option must be provided"}

    condition: Dict[str, Any] = {"type": condition_type.upper()}
    if condition_values:
        condition["values"] = [{"userEnteredValue": v} for v in condition_values]

    rule: Dict[str, Any] = {
        "ranges": [{"sheetId": sheet_id, **range_indices}],
        "booleanRule": {
            "condition": condition,
            "format": cell_format,
        },
    }

    return (
        sheets_service.spreadsheets()
        .batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {"addConditionalFormatRule": {"rule": rule, "index": 0}}
                ]
            },
        )
        .execute()
    )


def get_conditional_formatting(
    spreadsheet_id: str,
    sheet: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get all conditional formatting rules for a sheet."""
    sheets_service = ctx.request_context.lifespan_context.sheets_service
    try:
        sheet_id = get_sheet_id_or_error(sheets_service, spreadsheet_id, sheet)
    except SheetNotFoundError as e:
        return {"error": str(e)}

    result = (
        sheets_service.spreadsheets()
        .get(
            spreadsheetId=spreadsheet_id,
            fields="sheets(properties(sheetId,title),conditionalFormats)",
        )
        .execute()
    )

    for s in result.get("sheets", []):
        if s["properties"]["sheetId"] == sheet_id:
            return {
                "spreadsheetId": spreadsheet_id,
                "sheet": sheet,
                "conditionalFormats": s.get("conditionalFormats", []),
            }

    return {"spreadsheetId": spreadsheet_id, "sheet": sheet, "conditionalFormats": []}


def delete_conditional_formatting(
    spreadsheet_id: str,
    sheet: str,
    index: int,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Delete a conditional formatting rule by its 0-based index."""
    sheets_service = ctx.request_context.lifespan_context.sheets_service
    try:
        sheet_id = get_sheet_id_or_error(sheets_service, spreadsheet_id, sheet)
    except SheetNotFoundError as e:
        return {"error": str(e)}

    if index < 0:
        return {"error": "index must be >= 0"}

    return (
        sheets_service.spreadsheets()
        .batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {
                        "deleteConditionalFormatRule": {
                            "sheetId": sheet_id,
                            "index": index,
                        }
                    }
                ]
            },
        )
        .execute()
    )


def delete_chart(
    spreadsheet_id: str,
    chart_id: int,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Delete a chart from a spreadsheet by chart ID."""
    sheets_service = ctx.request_context.lifespan_context.sheets_service

    return (
        sheets_service.spreadsheets()
        .batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [{"deleteEmbeddedObject": {"objectId": chart_id}}]
            },
        )
        .execute()
    )


def copy_formatting(
    spreadsheet_id: str,
    source_sheet: str,
    source_range: str,
    destination_sheet: str,
    destination_range: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Copy cell formatting from a source range to a destination range.

    Only formatting is copied — cell values are not changed.
    Source and destination ranges must be the same size.
    """
    sheets_service = ctx.request_context.lifespan_context.sheets_service
    try:
        src_id = get_sheet_id_or_error(sheets_service, spreadsheet_id, source_sheet)
    except SheetNotFoundError as e:
        return {"error": str(e)}
    try:
        dst_id = get_sheet_id_or_error(sheets_service, spreadsheet_id, destination_sheet)
    except SheetNotFoundError as e:
        return {"error": str(e)}

    try:
        src_indices = parse_a1_notation(source_range)
        dst_indices = parse_a1_notation(destination_range)
    except ValueError as e:
        return {"error": str(e)}

    return (
        sheets_service.spreadsheets()
        .batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {
                        "copyPaste": {
                            "source": {"sheetId": src_id, **src_indices},
                            "destination": {"sheetId": dst_id, **dst_indices},
                            "pasteType": "PASTE_FORMAT",
                            "pasteOrientation": "NORMAL",
                        }
                    }
                ]
            },
        )
        .execute()
    )


def group_rows(
    spreadsheet_id: str,
    sheet: str,
    start_row: int,
    end_row: int,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Group rows together so they can be collapsed/expanded.

    ``start_row`` and ``end_row`` are 0-based indices (end exclusive).
    """
    sheets_service = ctx.request_context.lifespan_context.sheets_service
    try:
        sheet_id = get_sheet_id_or_error(sheets_service, spreadsheet_id, sheet)
    except SheetNotFoundError as e:
        return {"error": str(e)}

    if start_row < 0:
        return {"error": "start_row must be >= 0"}
    if end_row <= start_row:
        return {"error": "end_row must be greater than start_row"}

    return (
        sheets_service.spreadsheets()
        .batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {
                        "addDimensionGroup": {
                            "range": {
                                "sheetId": sheet_id,
                                "dimension": "ROWS",
                                "startIndex": start_row,
                                "endIndex": end_row,
                            }
                        }
                    }
                ]
            },
        )
        .execute()
    )


def ungroup_rows(
    spreadsheet_id: str,
    sheet: str,
    start_row: int,
    end_row: int,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Remove row grouping from a range.

    ``start_row`` and ``end_row`` are 0-based indices (end exclusive).
    """
    sheets_service = ctx.request_context.lifespan_context.sheets_service
    try:
        sheet_id = get_sheet_id_or_error(sheets_service, spreadsheet_id, sheet)
    except SheetNotFoundError as e:
        return {"error": str(e)}

    if start_row < 0:
        return {"error": "start_row must be >= 0"}
    if end_row <= start_row:
        return {"error": "end_row must be greater than start_row"}

    return (
        sheets_service.spreadsheets()
        .batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {
                        "deleteDimensionGroup": {
                            "range": {
                                "sheetId": sheet_id,
                                "dimension": "ROWS",
                                "startIndex": start_row,
                                "endIndex": end_row,
                            }
                        }
                    }
                ]
            },
        )
        .execute()
    )


def group_columns(
    spreadsheet_id: str,
    sheet: str,
    start_column: int,
    end_column: int,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Group columns together so they can be collapsed/expanded.

    ``start_column`` and ``end_column`` are 0-based indices (end exclusive).
    """
    sheets_service = ctx.request_context.lifespan_context.sheets_service
    try:
        sheet_id = get_sheet_id_or_error(sheets_service, spreadsheet_id, sheet)
    except SheetNotFoundError as e:
        return {"error": str(e)}

    if start_column < 0:
        return {"error": "start_column must be >= 0"}
    if end_column <= start_column:
        return {"error": "end_column must be greater than start_column"}

    return (
        sheets_service.spreadsheets()
        .batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {
                        "addDimensionGroup": {
                            "range": {
                                "sheetId": sheet_id,
                                "dimension": "COLUMNS",
                                "startIndex": start_column,
                                "endIndex": end_column,
                            }
                        }
                    }
                ]
            },
        )
        .execute()
    )


def ungroup_columns(
    spreadsheet_id: str,
    sheet: str,
    start_column: int,
    end_column: int,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Remove column grouping from a range.

    ``start_column`` and ``end_column`` are 0-based indices (end exclusive).
    """
    sheets_service = ctx.request_context.lifespan_context.sheets_service
    try:
        sheet_id = get_sheet_id_or_error(sheets_service, spreadsheet_id, sheet)
    except SheetNotFoundError as e:
        return {"error": str(e)}

    if start_column < 0:
        return {"error": "start_column must be >= 0"}
    if end_column <= start_column:
        return {"error": "end_column must be greater than start_column"}

    return (
        sheets_service.spreadsheets()
        .batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {
                        "deleteDimensionGroup": {
                            "range": {
                                "sheetId": sheet_id,
                                "dimension": "COLUMNS",
                                "startIndex": start_column,
                                "endIndex": end_column,
                            }
                        }
                    }
                ]
            },
        )
        .execute()
    )


def register(registry: ToolRegistry) -> None:
    """Register all Sheets formatting tools in the registry."""
    registry.register(
        name="format_cells",
        description=(
            "Apply formatting to cells in a range: bold, italic, font size, "
            "font family, text/background color, alignment, wrap strategy, "
            "and number format."
        ),
        parameters=[
            ToolParameter(
                "spreadsheet_id", "string", "The ID of the spreadsheet (from URL)"
            ),
            ToolParameter("sheet", "string", "The name of the sheet/tab"),
            ToolParameter(
                "range", "string", "Cell range in A1 notation (e.g., 'A1:C3')"
            ),
            ToolParameter("bold", "boolean", "Bold text", required=False),
            ToolParameter("italic", "boolean", "Italic text", required=False),
            ToolParameter(
                "font_size", "integer", "Font size in points", required=False
            ),
            ToolParameter(
                "font_family",
                "string",
                "Font family name (e.g., 'Arial')",
                required=False,
            ),
            ToolParameter(
                "foreground_color",
                "object",
                "Text color as {red, green, blue} 0.0-1.0",
                required=False,
            ),
            ToolParameter(
                "background_color",
                "object",
                "Background color as {red, green, blue} 0.0-1.0",
                required=False,
            ),
            ToolParameter(
                "horizontal_alignment",
                "string",
                "LEFT, CENTER, or RIGHT",
                required=False,
            ),
            ToolParameter(
                "vertical_alignment",
                "string",
                "TOP, MIDDLE, or BOTTOM",
                required=False,
            ),
            ToolParameter(
                "wrap_strategy",
                "string",
                "OVERFLOW_CELL, LEGACY_WRAP, CLIP, or WRAP",
                required=False,
            ),
            ToolParameter(
                "number_format_type",
                "string",
                (
                    "Number format type: TEXT, NUMBER, PERCENT, CURRENCY, "
                    "DATE, TIME, DATE_TIME, SCIENTIFIC"
                ),
                required=False,
            ),
            ToolParameter(
                "number_format_pattern",
                "string",
                "Custom number format pattern (e.g., '#,##0.00')",
                required=False,
            ),
        ],
        tags=["sheets", "format", "style", "cells", "bold", "color", "alignment"],
        fn=format_cells,
    )

    registry.register(
        name="read_cell_format",
        description="Read the formatting information of cells in a range.",
        parameters=[
            ToolParameter(
                "spreadsheet_id", "string", "The ID of the spreadsheet (from URL)"
            ),
            ToolParameter("sheet", "string", "The name of the sheet/tab"),
            ToolParameter(
                "range", "string", "Cell range in A1 notation (e.g., 'A1:C3')"
            ),
        ],
        tags=["sheets", "read", "format", "style", "cells", "get"],
        fn=read_cell_format,
        read_only=True,
    )

    registry.register(
        name="freeze_rows_columns",
        description=(
            "Freeze rows and/or columns in a sheet to keep them visible "
            "while scrolling. Set frozen_rows=0 and frozen_columns=0 to unfreeze."
        ),
        parameters=[
            ToolParameter(
                "spreadsheet_id", "string", "The ID of the spreadsheet (from URL)"
            ),
            ToolParameter("sheet", "string", "The name of the sheet/tab"),
            ToolParameter(
                "frozen_rows",
                "integer",
                "Number of rows to freeze (default: 0)",
                required=False,
                default=0,
            ),
            ToolParameter(
                "frozen_columns",
                "integer",
                "Number of columns to freeze (default: 0)",
                required=False,
                default=0,
            ),
        ],
        tags=["sheets", "freeze", "rows", "columns", "pane", "lock", "header"],
        fn=freeze_rows_columns,
    )

    registry.register(
        name="set_column_widths",
        description="Set the pixel width of a range of columns.",
        parameters=[
            ToolParameter(
                "spreadsheet_id", "string", "The ID of the spreadsheet (from URL)"
            ),
            ToolParameter("sheet", "string", "The name of the sheet/tab"),
            ToolParameter("start_column", "integer", "0-based start column index"),
            ToolParameter(
                "end_column", "integer", "0-based end column index (exclusive)"
            ),
            ToolParameter("width", "integer", "Column width in pixels"),
        ],
        tags=["sheets", "column", "width", "resize", "dimension", "format"],
        fn=set_column_widths,
    )

    registry.register(
        name="set_row_heights",
        description="Set the pixel height of a range of rows.",
        parameters=[
            ToolParameter(
                "spreadsheet_id", "string", "The ID of the spreadsheet (from URL)"
            ),
            ToolParameter("sheet", "string", "The name of the sheet/tab"),
            ToolParameter("start_row", "integer", "0-based start row index"),
            ToolParameter(
                "end_row", "integer", "0-based end row index (exclusive)"
            ),
            ToolParameter("height", "integer", "Row height in pixels"),
        ],
        tags=["sheets", "row", "height", "resize", "dimension", "format"],
        fn=set_row_heights,
    )

    registry.register(
        name="auto_resize_columns",
        description="Auto-resize columns to fit their content.",
        parameters=[
            ToolParameter(
                "spreadsheet_id", "string", "The ID of the spreadsheet (from URL)"
            ),
            ToolParameter("sheet", "string", "The name of the sheet/tab"),
            ToolParameter(
                "start_column",
                "integer",
                "0-based start column index (default: 0)",
                required=False,
                default=0,
            ),
            ToolParameter(
                "end_column",
                "integer",
                "0-based end column index (exclusive). Omit for all columns.",
                required=False,
            ),
        ],
        tags=["sheets", "auto", "resize", "columns", "fit", "dimension"],
        fn=auto_resize_columns,
    )

    registry.register(
        name="auto_resize_rows",
        description="Auto-resize rows to fit their content.",
        parameters=[
            ToolParameter(
                "spreadsheet_id", "string", "The ID of the spreadsheet (from URL)"
            ),
            ToolParameter("sheet", "string", "The name of the sheet/tab"),
            ToolParameter(
                "start_row",
                "integer",
                "0-based start row index (default: 0)",
                required=False,
                default=0,
            ),
            ToolParameter(
                "end_row",
                "integer",
                "0-based end row index (exclusive). Omit for all rows.",
                required=False,
            ),
        ],
        tags=["sheets", "auto", "resize", "rows", "fit", "dimension"],
        fn=auto_resize_rows,
    )

    registry.register(
        name="set_dropdown_validation",
        description=(
            "Create a dropdown list data validation rule for a cell range. "
            "Users can only enter values from the provided list."
        ),
        parameters=[
            ToolParameter(
                "spreadsheet_id", "string", "The ID of the spreadsheet (from URL)"
            ),
            ToolParameter("sheet", "string", "The name of the sheet/tab"),
            ToolParameter(
                "range",
                "string",
                "Cell range in A1 notation (e.g., 'A1:A10')",
            ),
            ToolParameter(
                "values", "array", "List of allowed string values for the dropdown"
            ),
            ToolParameter(
                "strict",
                "boolean",
                "Reject invalid input (default: true)",
                required=False,
                default=True,
            ),
            ToolParameter(
                "show_dropdown",
                "boolean",
                "Show dropdown arrow in cell (default: true)",
                required=False,
                default=True,
            ),
        ],
        tags=["sheets", "validation", "dropdown", "list", "restrict", "data"],
        fn=set_dropdown_validation,
    )

    registry.register(
        name="protect_range",
        description=(
            "Protect a range or entire sheet from editing. "
            "Use warning_only=true for a soft warning instead of blocking edits."
        ),
        parameters=[
            ToolParameter(
                "spreadsheet_id", "string", "The ID of the spreadsheet (from URL)"
            ),
            ToolParameter("sheet", "string", "The name of the sheet/tab to protect"),
            ToolParameter(
                "range",
                "string",
                "Cell range in A1 notation. Omit to protect the entire sheet.",
                required=False,
            ),
            ToolParameter(
                "description",
                "string",
                "Description for the protection",
                required=False,
            ),
            ToolParameter(
                "warning_only",
                "boolean",
                "Show warning instead of blocking edits (default: false)",
                required=False,
                default=False,
            ),
        ],
        tags=["sheets", "protect", "lock", "range", "permission", "restrict"],
        fn=protect_range,
    )

    registry.register(
        name="add_conditional_formatting",
        description=(
            "Add a conditional formatting rule to a range. "
            "Applies formatting when the condition is met. "
            "Common condition_type values: NUMBER_GREATER, NUMBER_LESS, "
            "NUMBER_EQ, TEXT_CONTAINS, TEXT_EQ, BLANK, NOT_BLANK, CUSTOM_FORMULA."
        ),
        parameters=[
            ToolParameter(
                "spreadsheet_id", "string", "The ID of the spreadsheet (from URL)"
            ),
            ToolParameter("sheet", "string", "The name of the sheet/tab"),
            ToolParameter("range", "string", "Cell range in A1 notation"),
            ToolParameter(
                "condition_type",
                "string",
                (
                    "Condition type: NUMBER_GREATER, NUMBER_LESS, NUMBER_EQ, "
                    "TEXT_CONTAINS, TEXT_EQ, BLANK, NOT_BLANK, CUSTOM_FORMULA"
                ),
            ),
            ToolParameter(
                "condition_values",
                "array",
                "Values for the condition (e.g., ['100'] for NUMBER_GREATER).",
                required=False,
            ),
            ToolParameter(
                "format_bold", "boolean", "Apply bold formatting", required=False
            ),
            ToolParameter(
                "format_italic", "boolean", "Apply italic formatting", required=False
            ),
            ToolParameter(
                "format_background_color",
                "object",
                "Background color as {red, green, blue} 0.0-1.0",
                required=False,
            ),
            ToolParameter(
                "format_foreground_color",
                "object",
                "Text color as {red, green, blue} 0.0-1.0",
                required=False,
            ),
        ],
        tags=["sheets", "conditional", "formatting", "rules", "highlight", "style"],
        fn=add_conditional_formatting,
    )

    registry.register(
        name="get_conditional_formatting",
        description="Get all conditional formatting rules for a sheet.",
        parameters=[
            ToolParameter(
                "spreadsheet_id", "string", "The ID of the spreadsheet (from URL)"
            ),
            ToolParameter("sheet", "string", "The name of the sheet/tab"),
        ],
        tags=["sheets", "conditional", "formatting", "rules", "read", "get"],
        fn=get_conditional_formatting,
        read_only=True,
    )

    registry.register(
        name="delete_conditional_formatting",
        description=(
            "Delete a conditional formatting rule by its 0-based index. "
            "Use get_conditional_formatting to find rule indices."
        ),
        parameters=[
            ToolParameter(
                "spreadsheet_id", "string", "The ID of the spreadsheet (from URL)"
            ),
            ToolParameter("sheet", "string", "The name of the sheet/tab"),
            ToolParameter(
                "index", "integer", "0-based index of the rule to delete"
            ),
        ],
        tags=["sheets", "conditional", "formatting", "delete", "remove", "rules"],
        fn=delete_conditional_formatting,
    )

    registry.register(
        name="delete_chart",
        description=(
            "Delete a chart from a spreadsheet by its chart ID. "
            "Use get_sheet_data with include_grid_data=true to find chart IDs, "
            "or list them via the Sheets API charts endpoint."
        ),
        parameters=[
            ToolParameter(
                "spreadsheet_id", "string", "The ID of the spreadsheet (from URL)"
            ),
            ToolParameter("chart_id", "integer", "The chart ID to delete"),
        ],
        tags=["sheets", "chart", "delete", "remove", "embedded"],
        fn=delete_chart,
    )

    registry.register(
        name="copy_formatting",
        description=(
            "Copy cell formatting from a source range to a destination range. "
            "Only formatting is copied — cell values are unchanged. "
            "Source and destination ranges must be the same size."
        ),
        parameters=[
            ToolParameter(
                "spreadsheet_id", "string", "The ID of the spreadsheet (from URL)"
            ),
            ToolParameter("source_sheet", "string", "Name of the source sheet/tab"),
            ToolParameter(
                "source_range", "string", "Source cell range in A1 notation"
            ),
            ToolParameter(
                "destination_sheet",
                "string",
                "Name of the destination sheet/tab",
            ),
            ToolParameter(
                "destination_range",
                "string",
                "Destination cell range in A1 notation (same size as source)",
            ),
        ],
        tags=["sheets", "copy", "format", "paste", "style", "clone"],
        fn=copy_formatting,
    )

    registry.register(
        name="group_rows",
        description=(
            "Group rows together so they can be collapsed and expanded. "
            "Indices are 0-based, end_row is exclusive."
        ),
        parameters=[
            ToolParameter(
                "spreadsheet_id", "string", "The ID of the spreadsheet (from URL)"
            ),
            ToolParameter("sheet", "string", "The name of the sheet/tab"),
            ToolParameter("start_row", "integer", "0-based start row index"),
            ToolParameter(
                "end_row", "integer", "0-based end row index (exclusive)"
            ),
        ],
        tags=["sheets", "group", "rows", "collapse", "expand", "outline"],
        fn=group_rows,
    )

    registry.register(
        name="ungroup_rows",
        description=(
            "Remove row grouping from a range. "
            "Indices are 0-based, end_row is exclusive."
        ),
        parameters=[
            ToolParameter(
                "spreadsheet_id", "string", "The ID of the spreadsheet (from URL)"
            ),
            ToolParameter("sheet", "string", "The name of the sheet/tab"),
            ToolParameter("start_row", "integer", "0-based start row index"),
            ToolParameter(
                "end_row", "integer", "0-based end row index (exclusive)"
            ),
        ],
        tags=["sheets", "ungroup", "rows", "expand", "outline", "remove"],
        fn=ungroup_rows,
    )

    registry.register(
        name="group_columns",
        description=(
            "Group columns together so they can be collapsed and expanded. "
            "Indices are 0-based, end_column is exclusive."
        ),
        parameters=[
            ToolParameter(
                "spreadsheet_id", "string", "The ID of the spreadsheet (from URL)"
            ),
            ToolParameter("sheet", "string", "The name of the sheet/tab"),
            ToolParameter("start_column", "integer", "0-based start column index"),
            ToolParameter(
                "end_column", "integer", "0-based end column index (exclusive)"
            ),
        ],
        tags=["sheets", "group", "columns", "collapse", "expand", "outline"],
        fn=group_columns,
    )

    registry.register(
        name="ungroup_columns",
        description=(
            "Remove column grouping from a range. "
            "Indices are 0-based, end_column is exclusive."
        ),
        parameters=[
            ToolParameter(
                "spreadsheet_id", "string", "The ID of the spreadsheet (from URL)"
            ),
            ToolParameter("sheet", "string", "The name of the sheet/tab"),
            ToolParameter("start_column", "integer", "0-based start column index"),
            ToolParameter(
                "end_column", "integer", "0-based end column index (exclusive)"
            ),
        ],
        tags=["sheets", "ungroup", "columns", "expand", "outline", "remove"],
        fn=ungroup_columns,
    )
