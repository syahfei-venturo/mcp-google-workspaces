"""Write operations for Google Sheets."""

from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import Context

from ...registry import ToolParameter, ToolRegistry
from ...utils.sheets import get_sheet_id, parse_a1_notation


def update_cells(
    spreadsheet_id: str,
    sheet: str,
    range: str,
    data: List[List[Any]],
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Update cells in a Google Spreadsheet."""
    sheets_service = ctx.request_context.lifespan_context.sheets_service
    full_range = f"{sheet}!{range}"

    return (
        sheets_service.spreadsheets()
        .values()
        .update(
            spreadsheetId=spreadsheet_id,
            range=full_range,
            valueInputOption="USER_ENTERED",
            body={"values": data},
        )
        .execute()
    )


def batch_update_cells(
    spreadsheet_id: str,
    sheet: str,
    ranges: Dict[str, List[List[Any]]],
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Batch update multiple ranges in one API call."""
    sheets_service = ctx.request_context.lifespan_context.sheets_service

    data = [
        {"range": f"{sheet}!{range_str}", "values": values}
        for range_str, values in ranges.items()
    ]

    return (
        sheets_service.spreadsheets()
        .values()
        .batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"valueInputOption": "USER_ENTERED", "data": data},
        )
        .execute()
    )


def batch_update(
    spreadsheet_id: str,
    requests: List[Dict[str, Any]],
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Execute a batch update using the full batchUpdate endpoint.

    Provides access to all batchUpdate operations: addSheet,
    updateSheetProperties, insertDimension, deleteDimension,
    updateCells, updateBorders, conditionalFormatting, etc.
    """
    sheets_service = ctx.request_context.lifespan_context.sheets_service

    if not requests:
        return {"error": "requests list cannot be empty"}
    if not all(isinstance(req, dict) for req in requests):
        return {"error": "Each request must be a dictionary"}

    return (
        sheets_service.spreadsheets()
        .batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": requests},
        )
        .execute()
    )


def add_rows(
    spreadsheet_id: str,
    sheet: str,
    count: int,
    start_row: Optional[int] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Add rows to a sheet at a specified position."""
    sheets_service = ctx.request_context.lifespan_context.sheets_service
    sheet_id = get_sheet_id(sheets_service, spreadsheet_id, sheet)

    if sheet_id is None:
        return {"error": f"Sheet '{sheet}' not found"}

    start = start_row if start_row is not None else 0
    return (
        sheets_service.spreadsheets()
        .batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {
                        "insertDimension": {
                            "range": {
                                "sheetId": sheet_id,
                                "dimension": "ROWS",
                                "startIndex": start,
                                "endIndex": start + count,
                            },
                            "inheritFromBefore": start > 0,
                        }
                    }
                ]
            },
        )
        .execute()
    )


def add_columns(
    spreadsheet_id: str,
    sheet: str,
    count: int,
    start_column: Optional[int] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Add columns to a sheet at a specified position."""
    sheets_service = ctx.request_context.lifespan_context.sheets_service
    sheet_id = get_sheet_id(sheets_service, spreadsheet_id, sheet)

    if sheet_id is None:
        return {"error": f"Sheet '{sheet}' not found"}

    start = start_column if start_column is not None else 0
    return (
        sheets_service.spreadsheets()
        .batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {
                        "insertDimension": {
                            "range": {
                                "sheetId": sheet_id,
                                "dimension": "COLUMNS",
                                "startIndex": start,
                                "endIndex": start + count,
                            },
                            "inheritFromBefore": start > 0,
                        }
                    }
                ]
            },
        )
        .execute()
    )


def append_rows(
    spreadsheet_id: str,
    sheet: str,
    data: List[List[Any]],
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Append rows of data to the end of a sheet."""
    sheets_service = ctx.request_context.lifespan_context.sheets_service

    return (
        sheets_service.spreadsheets()
        .values()
        .append(
            spreadsheetId=spreadsheet_id,
            range=sheet,
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": data},
        )
        .execute()
    )


def clear_range(
    spreadsheet_id: str,
    sheet: str,
    range: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Clear cell contents in a range without deleting the cells."""
    sheets_service = ctx.request_context.lifespan_context.sheets_service
    full_range = f"{sheet}!{range}"

    return (
        sheets_service.spreadsheets()
        .values()
        .clear(
            spreadsheetId=spreadsheet_id,
            range=full_range,
            body={},
        )
        .execute()
    )


def delete_rows(
    spreadsheet_id: str,
    sheet: str,
    start_row: int,
    count: int,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Delete rows from a sheet."""
    sheets_service = ctx.request_context.lifespan_context.sheets_service
    sheet_id = get_sheet_id(sheets_service, spreadsheet_id, sheet)

    if sheet_id is None:
        return {"error": f"Sheet '{sheet}' not found"}

    return (
        sheets_service.spreadsheets()
        .batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {
                        "deleteDimension": {
                            "range": {
                                "sheetId": sheet_id,
                                "dimension": "ROWS",
                                "startIndex": start_row,
                                "endIndex": start_row + count,
                            }
                        }
                    }
                ]
            },
        )
        .execute()
    )


def delete_columns(
    spreadsheet_id: str,
    sheet: str,
    start_column: int,
    count: int,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Delete columns from a sheet."""
    sheets_service = ctx.request_context.lifespan_context.sheets_service
    sheet_id = get_sheet_id(sheets_service, spreadsheet_id, sheet)

    if sheet_id is None:
        return {"error": f"Sheet '{sheet}' not found"}

    return (
        sheets_service.spreadsheets()
        .batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {
                        "deleteDimension": {
                            "range": {
                                "sheetId": sheet_id,
                                "dimension": "COLUMNS",
                                "startIndex": start_column,
                                "endIndex": start_column + count,
                            }
                        }
                    }
                ]
            },
        )
        .execute()
    )


def sort_range(
    spreadsheet_id: str,
    sheet: str,
    range: str,
    sort_column: int,
    ascending: bool = True,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Sort a range of cells by a specific column."""
    sheets_service = ctx.request_context.lifespan_context.sheets_service
    sheet_id = get_sheet_id(sheets_service, spreadsheet_id, sheet)

    if sheet_id is None:
        return {"error": f"Sheet '{sheet}' not found"}

    try:
        range_indices = parse_a1_notation(range)
    except ValueError as e:
        return {"error": str(e)}

    return (
        sheets_service.spreadsheets()
        .batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {
                        "sortRange": {
                            "range": {
                                "sheetId": sheet_id,
                                **range_indices,
                            },
                            "sortSpecs": [
                                {
                                    "dimensionIndex": sort_column,
                                    "sortOrder": (
                                        "ASCENDING" if ascending else "DESCENDING"
                                    ),
                                }
                            ],
                        }
                    }
                ]
            },
        )
        .execute()
    )


def merge_cells(
    spreadsheet_id: str,
    sheet: str,
    range: str,
    merge_type: str = "MERGE_ALL",
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Merge cells in a range."""
    sheets_service = ctx.request_context.lifespan_context.sheets_service
    sheet_id = get_sheet_id(sheets_service, spreadsheet_id, sheet)

    if sheet_id is None:
        return {"error": f"Sheet '{sheet}' not found"}

    valid_types = ["MERGE_ALL", "MERGE_COLUMNS", "MERGE_ROWS"]
    if merge_type.upper() not in valid_types:
        return {
            "error": (
                f"Invalid merge_type '{merge_type}'. "
                f"Must be one of: {', '.join(valid_types)}"
            )
        }

    try:
        range_indices = parse_a1_notation(range)
    except ValueError as e:
        return {"error": str(e)}

    return (
        sheets_service.spreadsheets()
        .batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {
                        "mergeCells": {
                            "range": {
                                "sheetId": sheet_id,
                                **range_indices,
                            },
                            "mergeType": merge_type.upper(),
                        }
                    }
                ]
            },
        )
        .execute()
    )


def unmerge_cells(
    spreadsheet_id: str,
    sheet: str,
    range: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Unmerge previously merged cells in a range."""
    sheets_service = ctx.request_context.lifespan_context.sheets_service
    sheet_id = get_sheet_id(sheets_service, spreadsheet_id, sheet)

    if sheet_id is None:
        return {"error": f"Sheet '{sheet}' not found"}

    try:
        range_indices = parse_a1_notation(range)
    except ValueError as e:
        return {"error": str(e)}

    return (
        sheets_service.spreadsheets()
        .batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {
                        "unmergeCells": {
                            "range": {
                                "sheetId": sheet_id,
                                **range_indices,
                            }
                        }
                    }
                ]
            },
        )
        .execute()
    )


def register(registry: ToolRegistry) -> None:
    """Register all Sheets write tools in the registry."""
    registry.register(
        name="update_cells",
        description=(
            "Write data to a specific range in a sheet. Overwrites existing data."
        ),
        parameters=[
            ToolParameter(
                "spreadsheet_id",
                "string",
                "The ID of the spreadsheet (from URL)",
            ),
            ToolParameter("sheet", "string", "The name of the sheet/tab"),
            ToolParameter(
                "range",
                "string",
                "Cell range in A1 notation (e.g., 'A1:C3')",
            ),
            ToolParameter(
                "data",
                "array",
                "2D array of values to write. E.g., [[1,2],[3,4]]",
            ),
        ],
        tags=["sheets", "write", "update", "cells", "values", "edit", "set"],
        fn=update_cells,
    )

    registry.register(
        name="batch_update_cells",
        description=(
            "Update multiple ranges in one API call. "
            "More efficient than multiple update_cells calls."
        ),
        parameters=[
            ToolParameter(
                "spreadsheet_id",
                "string",
                "The ID of the spreadsheet (from URL)",
            ),
            ToolParameter("sheet", "string", "The name of the sheet/tab"),
            ToolParameter(
                "ranges",
                "object",
                "Dict mapping range strings to 2D value arrays. "
                "E.g., {'A1:B2': [[1,2],[3,4]]}",
            ),
        ],
        tags=["sheets", "write", "update", "batch", "cells", "multiple", "efficient"],
        fn=batch_update_cells,
    )

    registry.register(
        name="batch_update",
        description=(
            "Execute raw batchUpdate requests. Access all Sheets API "
            "operations: formatting, borders, conditional formatting, "
            "dimension properties, etc."
        ),
        parameters=[
            ToolParameter(
                "spreadsheet_id",
                "string",
                "The ID of the spreadsheet (from URL)",
            ),
            ToolParameter(
                "requests",
                "array",
                "List of batchUpdate request objects "
                "(addSheet, updateCells, updateBorders, etc.)",
            ),
        ],
        tags=[
            "sheets",
            "write",
            "batch",
            "format",
            "advanced",
            "raw",
            "api",
            "borders",
            "style",
        ],
        fn=batch_update,
    )

    registry.register(
        name="add_rows",
        description="Insert empty rows into a sheet at a specified position.",
        parameters=[
            ToolParameter(
                "spreadsheet_id",
                "string",
                "The ID of the spreadsheet (from URL)",
            ),
            ToolParameter("sheet", "string", "The name of the sheet/tab"),
            ToolParameter("count", "integer", "Number of rows to insert"),
            ToolParameter(
                "start_row",
                "integer",
                "0-based row index to insert at (default: 0)",
                required=False,
                default=0,
            ),
        ],
        tags=["sheets", "write", "rows", "insert", "add", "dimension"],
        fn=add_rows,
    )

    registry.register(
        name="add_columns",
        description="Insert empty columns into a sheet at a specified position.",
        parameters=[
            ToolParameter(
                "spreadsheet_id",
                "string",
                "The ID of the spreadsheet (from URL)",
            ),
            ToolParameter("sheet", "string", "The name of the sheet/tab"),
            ToolParameter("count", "integer", "Number of columns to insert"),
            ToolParameter(
                "start_column",
                "integer",
                "0-based column index to insert at (default: 0)",
                required=False,
                default=0,
            ),
        ],
        tags=["sheets", "write", "columns", "insert", "add", "dimension"],
        fn=add_columns,
    )

    registry.register(
        name="append_rows",
        description=(
            "Append rows of data to the end of a sheet. "
            "Automatically finds the next empty row."
        ),
        parameters=[
            ToolParameter(
                "spreadsheet_id",
                "string",
                "The ID of the spreadsheet (from URL)",
            ),
            ToolParameter("sheet", "string", "The name of the sheet/tab"),
            ToolParameter(
                "data",
                "array",
                "2D array of values to append. E.g., [['a','b'],['c','d']]",
            ),
        ],
        tags=["sheets", "write", "append", "rows", "add", "insert", "data"],
        fn=append_rows,
    )

    registry.register(
        name="clear_range",
        description=(
            "Clear cell contents in a range without deleting the cells themselves."
        ),
        parameters=[
            ToolParameter(
                "spreadsheet_id",
                "string",
                "The ID of the spreadsheet (from URL)",
            ),
            ToolParameter("sheet", "string", "The name of the sheet/tab"),
            ToolParameter(
                "range",
                "string",
                "Cell range in A1 notation (e.g., 'A1:C10')",
            ),
        ],
        tags=["sheets", "write", "clear", "erase", "empty", "cells", "range"],
        fn=clear_range,
    )

    registry.register(
        name="delete_rows",
        description="Delete rows from a sheet by position and count.",
        parameters=[
            ToolParameter(
                "spreadsheet_id",
                "string",
                "The ID of the spreadsheet (from URL)",
            ),
            ToolParameter("sheet", "string", "The name of the sheet/tab"),
            ToolParameter(
                "start_row",
                "integer",
                "0-based row index to start deleting from",
            ),
            ToolParameter("count", "integer", "Number of rows to delete"),
        ],
        tags=["sheets", "write", "delete", "rows", "remove", "dimension"],
        fn=delete_rows,
    )

    registry.register(
        name="delete_columns",
        description="Delete columns from a sheet by position and count.",
        parameters=[
            ToolParameter(
                "spreadsheet_id",
                "string",
                "The ID of the spreadsheet (from URL)",
            ),
            ToolParameter("sheet", "string", "The name of the sheet/tab"),
            ToolParameter(
                "start_column",
                "integer",
                "0-based column index to start deleting from",
            ),
            ToolParameter("count", "integer", "Number of columns to delete"),
        ],
        tags=["sheets", "write", "delete", "columns", "remove", "dimension"],
        fn=delete_columns,
    )

    registry.register(
        name="sort_range",
        description=(
            "Sort a range of cells by a specific column, ascending or descending."
        ),
        parameters=[
            ToolParameter(
                "spreadsheet_id",
                "string",
                "The ID of the spreadsheet (from URL)",
            ),
            ToolParameter("sheet", "string", "The name of the sheet/tab"),
            ToolParameter(
                "range",
                "string",
                "Cell range in A1 notation (e.g., 'A1:D20')",
            ),
            ToolParameter(
                "sort_column",
                "integer",
                "0-based column index within the range to sort by",
            ),
            ToolParameter(
                "ascending",
                "boolean",
                "Sort ascending (default: true)",
                required=False,
                default=True,
            ),
        ],
        tags=["sheets", "write", "sort", "order", "arrange", "range"],
        fn=sort_range,
    )

    registry.register(
        name="merge_cells",
        description=(
            "Merge cells in a range. Types: MERGE_ALL, MERGE_COLUMNS, MERGE_ROWS."
        ),
        parameters=[
            ToolParameter(
                "spreadsheet_id",
                "string",
                "The ID of the spreadsheet (from URL)",
            ),
            ToolParameter("sheet", "string", "The name of the sheet/tab"),
            ToolParameter(
                "range",
                "string",
                "Cell range in A1 notation (e.g., 'A1:C1')",
            ),
            ToolParameter(
                "merge_type",
                "string",
                "MERGE_ALL, MERGE_COLUMNS, or MERGE_ROWS (default: MERGE_ALL)",
                required=False,
                default="MERGE_ALL",
            ),
        ],
        tags=["sheets", "write", "merge", "cells", "combine", "format"],
        fn=merge_cells,
    )

    registry.register(
        name="unmerge_cells",
        description="Unmerge previously merged cells in a range.",
        parameters=[
            ToolParameter(
                "spreadsheet_id",
                "string",
                "The ID of the spreadsheet (from URL)",
            ),
            ToolParameter("sheet", "string", "The name of the sheet/tab"),
            ToolParameter(
                "range",
                "string",
                "Cell range in A1 notation (e.g., 'A1:C1')",
            ),
        ],
        tags=["sheets", "write", "unmerge", "cells", "split", "format"],
        fn=unmerge_cells,
    )
