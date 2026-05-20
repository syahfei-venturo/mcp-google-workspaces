"""Read operations for Google Sheets."""

import re
from typing import Any, Dict, List, Optional

from googleapiclient.errors import HttpError
from mcp.server.fastmcp import Context

from ...registry import ToolParameter, ToolRegistry
from ...utils.sheets import column_index_to_letter

_VALID_MATCH_TYPES = {"contains", "exact", "regex", "starts_with"}
_MAX_QUERY_LENGTH = 1000
_MAX_ROWS_TO_SCAN = 10000


def get_sheet_data(
    spreadsheet_id: str,
    sheet: str,
    range: Optional[str] = None,
    include_grid_data: bool = False,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get data from a specific sheet in a Google Spreadsheet."""
    sheets_service = ctx.request_context.lifespan_context.sheets_service
    full_range = f"{sheet}!{range}" if range else sheet

    if include_grid_data:
        return (
            sheets_service.spreadsheets()
            .get(
                spreadsheetId=spreadsheet_id,
                ranges=[full_range],
                includeGridData=True,
            )
            .execute()
        )

    values_result = (
        sheets_service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=full_range)
        .execute()
    )
    return {
        "spreadsheetId": spreadsheet_id,
        "valueRanges": [
            {
                "range": full_range,
                "values": values_result.get("values", []),
            }
        ],
    }


def get_sheet_formulas(
    spreadsheet_id: str,
    sheet: str,
    range: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> List[List[Any]]:
    """Get formulas from a specific sheet."""
    sheets_service = ctx.request_context.lifespan_context.sheets_service
    full_range = f"{sheet}!{range}" if range else sheet

    result = (
        sheets_service.spreadsheets()
        .values()
        .get(
            spreadsheetId=spreadsheet_id,
            range=full_range,
            valueRenderOption="FORMULA",
        )
        .execute()
    )
    return result.get("values", [])


def get_multiple_sheet_data(
    queries: List[Dict[str, str]],
    ctx: Optional[Context] = None,
) -> List[Dict[str, Any]]:
    """Get data from multiple specific ranges across spreadsheets."""
    sheets_service = ctx.request_context.lifespan_context.sheets_service
    results = []

    for query in queries:
        sid = query.get("spreadsheet_id")
        sheet = query.get("sheet")
        range_str = query.get("range")

        if not all([sid, sheet]):
            results.append(
                {
                    **query,
                    "error": "Missing required keys (spreadsheet_id, sheet)",
                }
            )
            continue

        try:
            full_range = f"{sheet}!{range_str}" if range_str else sheet
            result = (
                sheets_service.spreadsheets()
                .values()
                .get(spreadsheetId=sid, range=full_range)
                .execute()
            )
            results.append({**query, "data": result.get("values", [])})
        except HttpError as e:
            results.append({**query, "error": f"Google API error: {e}"})

    return results


def get_multiple_spreadsheet_summary(
    spreadsheet_ids: List[str],
    rows_to_fetch: int = 5,
    ctx: Optional[Context] = None,
) -> List[Dict[str, Any]]:
    """Get summary of multiple spreadsheets including headers and preview rows."""
    sheets_service = ctx.request_context.lifespan_context.sheets_service
    summaries = []

    for spreadsheet_id in spreadsheet_ids:
        summary_data: Dict[str, Any] = {
            "spreadsheet_id": spreadsheet_id,
            "title": None,
            "sheets": [],
            "error": None,
        }
        try:
            spreadsheet = (
                sheets_service.spreadsheets()
                .get(
                    spreadsheetId=spreadsheet_id,
                    fields="properties.title,sheets(properties(title,sheetId))",
                )
                .execute()
            )

            summary_data["title"] = spreadsheet.get("properties", {}).get(
                "title", "Unknown Title"
            )
            sheet_summaries = []

            for sheet in spreadsheet.get("sheets", []):
                sheet_title = sheet.get("properties", {}).get("title")
                sheet_id = sheet.get("properties", {}).get("sheetId")
                sheet_summary: Dict[str, Any] = {
                    "title": sheet_title,
                    "sheet_id": sheet_id,
                    "headers": [],
                    "first_rows": [],
                    "error": None,
                }

                if not sheet_title:
                    sheet_summary["error"] = "Sheet title not found"
                    sheet_summaries.append(sheet_summary)
                    continue

                try:
                    max_row = max(1, rows_to_fetch)
                    range_to_get = f"{sheet_title}!A1:{max_row}"
                    result = (
                        sheets_service.spreadsheets()
                        .values()
                        .get(spreadsheetId=spreadsheet_id, range=range_to_get)
                        .execute()
                    )
                    values = result.get("values", [])

                    if values:
                        sheet_summary["headers"] = values[0]
                        if len(values) > 1:
                            sheet_summary["first_rows"] = values[1:max_row]
                except HttpError as sheet_e:
                    sheet_summary["error"] = (
                        f"Error fetching data for sheet {sheet_title}: {sheet_e}"
                    )

                sheet_summaries.append(sheet_summary)

            summary_data["sheets"] = sheet_summaries
        except HttpError as e:
            summary_data["error"] = f"Error fetching spreadsheet {spreadsheet_id}: {e}"

        summaries.append(summary_data)
    return summaries


def _cell_matches(
    cell_str: str,
    query: str,
    match_type: str,
    case_sensitive: bool,
    compiled_regex: Optional["re.Pattern[str]"] = None,
) -> bool:
    """Check whether *cell_str* matches *query* under the given strategy."""
    if match_type == "regex":
        return compiled_regex.search(cell_str) is not None if compiled_regex else False

    compare = cell_str if case_sensitive else cell_str.lower()
    target = query if case_sensitive else query.lower()

    if match_type == "exact":
        return compare == target
    if match_type == "starts_with":
        return compare.startswith(target)
    # default: contains
    return target in compare


def _resolve_column_indices(
    headers: List[str],
    columns: List[str],
    case_sensitive: bool,
) -> List[int]:
    """Map column header names to their indices."""
    if case_sensitive:
        header_map = {h: i for i, h in enumerate(headers)}
    else:
        header_map = {h.lower(): i for i, h in enumerate(headers)}

    indices: List[int] = []
    for col in columns:
        key = col if case_sensitive else col.lower()
        if key in header_map:
            indices.append(header_map[key])
    return indices


def find_in_spreadsheet(
    spreadsheet_id: str,
    query: str,
    sheet: Optional[str] = None,
    match_type: str = "contains",
    columns: Optional[List[str]] = None,
    case_sensitive: bool = False,
    include_row_context: bool = False,
    max_results: int = 50,
    ctx: Optional[Context] = None,
) -> List[Dict[str, Any]]:
    """Find cells containing a specific value in a spreadsheet.

    Parameters
    ----------
    match_type : str
        Matching strategy: ``contains`` (default), ``exact``,
        ``starts_with``, or ``regex``.
    columns : list[str] | None
        Restrict search to columns matching these header names
        (first row is treated as headers).
    include_row_context : bool
        When ``True`` each result includes a ``row_data`` dict mapping
        header names to the full row values.
    """
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

    # Pre-compile regex if needed
    compiled_regex: Optional[re.Pattern[str]] = None
    if match_type == "regex":
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            compiled_regex = re.compile(query, flags)
        except re.error as exc:
            return {"error": f"Invalid regex pattern: {exc}"}

    sheets_service = ctx.request_context.lifespan_context.sheets_service
    results: List[Dict[str, Any]] = []

    spreadsheet = (
        sheets_service.spreadsheets()
        .get(
            spreadsheetId=spreadsheet_id,
            fields="sheets(properties(title,sheetId))",
        )
        .execute()
    )

    sheets_to_search = [
        s.get("properties", {}).get("title")
        for s in spreadsheet.get("sheets", [])
        if sheet is None or s.get("properties", {}).get("title") == sheet
    ]

    if not sheets_to_search:
        return {"error": f"Sheet '{sheet}' not found"}

    for sheet_name in sheets_to_search:
        if len(results) >= max_results:
            break

        # Limit rows fetched to prevent OOM on large sheets
        scan_range = f"{sheet_name}!A1:ZZ{_MAX_ROWS_TO_SCAN}"
        response = (
            sheets_service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=scan_range)
            .execute()
        )
        values = response.get("values", [])
        if not values:
            continue

        # Resolve headers and column filter
        headers = values[0] if values else []
        col_indices: Optional[List[int]] = None
        if columns is not None:
            col_indices = _resolve_column_indices(headers, columns, case_sensitive)
            if not col_indices:
                # None of the requested columns exist — skip sheet
                continue

        for row_idx, row in enumerate(values):
            if len(results) >= max_results:
                break

            search_cols = (
                col_indices if col_indices is not None else range(len(row))
            )

            for col_idx in search_cols:
                if len(results) >= max_results:
                    break
                if col_idx >= len(row):
                    continue

                cell_value = row[col_idx]
                cell_str = str(cell_value)

                if not _cell_matches(
                    cell_str, query, match_type, case_sensitive, compiled_regex
                ):
                    continue

                cell_ref = f"{column_index_to_letter(col_idx)}{row_idx + 1}"
                entry: Dict[str, Any] = {
                    "sheet": sheet_name,
                    "cell": cell_ref,
                    "value": cell_value,
                }

                if include_row_context and headers:
                    entry["row_data"] = {
                        h: (row[i] if i < len(row) else "")
                        for i, h in enumerate(headers)
                    }

                results.append(entry)

    return results


def register(registry: ToolRegistry) -> None:
    """Register all Sheets read tools in the registry."""
    registry.register(
        name="get_sheet_data",
        description=(
            "Get data from a specific sheet in a Google Spreadsheet. "
            "Returns cell values or full grid data with formatting."
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
                "Cell range in A1 notation (e.g., 'A1:C10'). Omit for all data.",
                required=False,
            ),
            ToolParameter(
                "include_grid_data",
                "boolean",
                "Include formatting metadata. Increases response size.",
                required=False,
                default=False,
            ),
        ],
        tags=["sheets", "read", "data", "values", "cells", "fetch", "get"],
        fn=get_sheet_data,
        read_only=True,
    )

    registry.register(
        name="get_sheet_formulas",
        description=(
            "Get formulas from a specific sheet. "
            "Returns the formula text rather than computed values."
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
                "Cell range in A1 notation. Omit for all formulas.",
                required=False,
            ),
        ],
        tags=["sheets", "read", "formulas", "cells", "get", "expression"],
        fn=get_sheet_formulas,
        read_only=True,
    )

    registry.register(
        name="get_multiple_sheet_data",
        description=(
            "Fetch data from multiple ranges across different spreadsheets in one call."
        ),
        parameters=[
            ToolParameter(
                "queries",
                "array",
                "List of {spreadsheet_id, sheet, range?} objects. "
                "range is optional — omit for all data.",
            ),
        ],
        tags=["sheets", "read", "data", "multiple", "batch", "fetch"],
        fn=get_multiple_sheet_data,
        read_only=True,
    )

    registry.register(
        name="get_multiple_spreadsheet_summary",
        description=(
            "Get titles, sheet names, headers, and first rows "
            "for multiple spreadsheets."
        ),
        parameters=[
            ToolParameter(
                "spreadsheet_ids",
                "array",
                "List of spreadsheet IDs to summarize",
            ),
            ToolParameter(
                "rows_to_fetch",
                "integer",
                "Number of rows to preview (default: 5)",
                required=False,
                default=5,
            ),
        ],
        tags=[
            "sheets",
            "read",
            "summary",
            "overview",
            "headers",
            "preview",
            "multiple",
        ],
        fn=get_multiple_spreadsheet_summary,
        read_only=True,
    )

    registry.register(
        name="find_in_spreadsheet",
        description=(
            "Find cells matching a query in a spreadsheet. "
            "Supports substring, exact, starts_with, and regex matching. "
            "Can filter by column headers and include full row context."
        ),
        parameters=[
            ToolParameter(
                "spreadsheet_id",
                "string",
                "The ID of the spreadsheet (from URL)",
            ),
            ToolParameter("query", "string", "Text or regex pattern to search for"),
            ToolParameter(
                "sheet",
                "string",
                "Specific sheet to search. Omit to search all.",
                required=False,
            ),
            ToolParameter(
                "match_type",
                "string",
                "Matching strategy: contains (default), exact, starts_with, or regex.",
                required=False,
                default="contains",
            ),
            ToolParameter(
                "columns",
                "array",
                "Restrict search to these column header names (first row as headers).",
                required=False,
            ),
            ToolParameter(
                "case_sensitive",
                "boolean",
                "Case-sensitive search (default: false)",
                required=False,
                default=False,
            ),
            ToolParameter(
                "include_row_context",
                "boolean",
                "Include full row data mapped to headers (default: false)",
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
        tags=["sheets", "search", "find", "cells", "lookup", "query", "value", "regex"],
        fn=find_in_spreadsheet,
        read_only=True,
    )
