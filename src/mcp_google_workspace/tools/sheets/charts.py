"""Chart creation operations for Google Sheets."""

from typing import Any, Dict, Optional

from mcp.server.fastmcp import Context

from googleapiclient.errors import HttpError

from ...registry import ToolParameter, ToolRegistry
from ...utils.sheets import get_sheet_id, parse_a1_notation

# Pixel bounds for chart position and dimensions
_MAX_CHART_OFFSET = 10000
_MAX_CHART_DIMENSION = 5000
_MIN_CHART_DIMENSION = 50

VALID_CHART_TYPES = [
    "COLUMN",
    "BAR",
    "LINE",
    "AREA",
    "PIE",
    "SCATTER",
    "COMBO",
    "HISTOGRAM",
]


def _build_pie_spec(
    source_range: Dict[str, Any],
    title: Optional[str],
) -> Dict[str, Any]:
    """Build chart spec for pie charts."""
    spec: Dict[str, Any] = {
        "pieChart": {
            "legendPosition": "RIGHT_LEGEND",
            "domain": {"sourceRange": {"sources": [source_range]}},
            "series": {"sourceRange": {"sources": [source_range]}},
        },
    }
    if title:
        spec["title"] = title
    return spec


def _build_basic_spec(
    chart_type: str,
    source_range: Dict[str, Any],
    title: Optional[str],
    x_axis_label: Optional[str],
    y_axis_label: Optional[str],
) -> Dict[str, Any]:
    """Build chart spec for all non-pie chart types."""
    spec: Dict[str, Any] = {
        "basicChart": {
            "chartType": chart_type,
            "legendPosition": "RIGHT_LEGEND",
            "axis": [
                {
                    "position": "BOTTOM_AXIS",
                    **({"title": x_axis_label} if x_axis_label else {}),
                },
                {
                    "position": "LEFT_AXIS",
                    **({"title": y_axis_label} if y_axis_label else {}),
                },
            ],
            "domains": [{"domain": {"sourceRange": {"sources": [source_range]}}}],
            "series": [
                {
                    "series": {"sourceRange": {"sources": [source_range]}},
                    "targetAxis": "LEFT_AXIS",
                }
            ],
            "headerCount": 1,
        },
    }
    if title:
        spec["title"] = title
    return spec


def _build_chart_request(
    chart_spec: Dict[str, Any],
    sheet_id: int,
    position_x: int,
    position_y: int,
    width: int,
    height: int,
) -> Dict[str, Any]:
    """Build the addChart batchUpdate request body."""
    return {
        "requests": [
            {
                "addChart": {
                    "chart": {
                        "spec": chart_spec,
                        "position": {
                            "overlayPosition": {
                                "anchorCell": {
                                    "sheetId": sheet_id,
                                    "rowIndex": 0,
                                    "columnIndex": 0,
                                },
                                "offsetXPixels": position_x,
                                "offsetYPixels": position_y,
                                "widthPixels": width,
                                "heightPixels": height,
                            }
                        },
                    }
                }
            }
        ]
    }


def add_chart(
    spreadsheet_id: str,
    sheet: str,
    chart_type: str,
    data_range: str,
    title: Optional[str] = None,
    x_axis_label: Optional[str] = None,
    y_axis_label: Optional[str] = None,
    position_x: int = 0,
    position_y: int = 0,
    width: int = 600,
    height: int = 400,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Add a chart to a Google Spreadsheet."""
    sheets_service = ctx.request_context.lifespan_context.sheets_service

    # Validate numeric parameters
    if position_x < 0 or position_x > _MAX_CHART_OFFSET:
        return {"error": f"position_x must be between 0 and {_MAX_CHART_OFFSET}"}
    if position_y < 0 or position_y > _MAX_CHART_OFFSET:
        return {"error": f"position_y must be between 0 and {_MAX_CHART_OFFSET}"}
    if width < _MIN_CHART_DIMENSION or width > _MAX_CHART_DIMENSION:
        return {
            "error": (
                f"width must be between {_MIN_CHART_DIMENSION} "
                f"and {_MAX_CHART_DIMENSION}"
            )
        }
    if height < _MIN_CHART_DIMENSION or height > _MAX_CHART_DIMENSION:
        return {
            "error": (
                f"height must be between {_MIN_CHART_DIMENSION} "
                f"and {_MAX_CHART_DIMENSION}"
            )
        }

    if chart_type.upper() not in VALID_CHART_TYPES:
        return {
            "error": (
                f"Invalid chart type '{chart_type}'. "
                f"Must be one of: {', '.join(VALID_CHART_TYPES)}"
            )
        }

    chart_type = chart_type.upper()
    sheet_id_val = get_sheet_id(sheets_service, spreadsheet_id, sheet)
    if sheet_id_val is None:
        return {"error": f"Sheet '{sheet}' not found in spreadsheet"}

    try:
        range_indices = parse_a1_notation(data_range)
    except ValueError as e:
        return {"error": str(e)}

    source_range = {"sheetId": sheet_id_val, **range_indices}

    if chart_type == "PIE":
        chart_spec = _build_pie_spec(source_range, title)
    else:
        chart_spec = _build_basic_spec(
            chart_type, source_range, title, x_axis_label, y_axis_label
        )

    request_body = _build_chart_request(
        chart_spec,
        sheet_id_val,
        position_x,
        position_y,
        width,
        height,
    )

    try:
        result = (
            sheets_service.spreadsheets()
            .batchUpdate(spreadsheetId=spreadsheet_id, body=request_body)
            .execute()
        )
        return {
            "success": True,
            "message": f"Chart '{title or chart_type}' added successfully",
            "chartId": (
                result.get("replies", [{}])[0]
                .get("addChart", {})
                .get("chart", {})
                .get("chartId")
            ),
            "result": result,
        }
    except HttpError as e:
        return {"error": f"Failed to add chart: {e}"}


def register(registry: ToolRegistry) -> None:
    """Register chart tools in the registry."""
    registry.register(
        name="add_chart",
        description=(
            "Create a chart (column, bar, line, area, pie, scatter, "
            "combo, histogram) from spreadsheet data."
        ),
        parameters=[
            ToolParameter(
                "spreadsheet_id",
                "string",
                "The ID of the spreadsheet (from URL)",
            ),
            ToolParameter(
                "sheet",
                "string",
                "Sheet name containing the data",
            ),
            ToolParameter(
                "chart_type",
                "string",
                "Chart type: COLUMN, BAR, LINE, AREA, PIE, "
                "SCATTER, COMBO, or HISTOGRAM",
            ),
            ToolParameter(
                "data_range",
                "string",
                "A1 notation range for chart data (e.g., 'A1:C10')",
            ),
            ToolParameter("title", "string", "Chart title", required=False),
            ToolParameter(
                "x_axis_label",
                "string",
                "X axis label",
                required=False,
            ),
            ToolParameter(
                "y_axis_label",
                "string",
                "Y axis label",
                required=False,
            ),
            ToolParameter(
                "position_x",
                "integer",
                "Horizontal offset in pixels (default: 0)",
                required=False,
                default=0,
            ),
            ToolParameter(
                "position_y",
                "integer",
                "Vertical offset in pixels (default: 0)",
                required=False,
                default=0,
            ),
            ToolParameter(
                "width",
                "integer",
                "Chart width in pixels (default: 600)",
                required=False,
                default=600,
            ),
            ToolParameter(
                "height",
                "integer",
                "Chart height in pixels (default: 400)",
                required=False,
                default=400,
            ),
        ],
        tags=[
            "sheets",
            "chart",
            "graph",
            "visualization",
            "plot",
            "diagram",
            "bar",
            "line",
            "pie",
        ],
        fn=add_chart,
    )
