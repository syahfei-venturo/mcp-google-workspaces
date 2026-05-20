"""Tests for tool functions with mocked Google API services."""

from unittest.mock import MagicMock

import httplib2
from googleapiclient.errors import HttpError

from mcp_google_workspace.tools.sheets.read import (
    find_in_spreadsheet,
    get_sheet_data,
    get_sheet_formulas,
)
from mcp_google_workspace.tools.sheets.write import (
    append_rows,
    clear_range,
    delete_columns,
    delete_rows,
    update_cells,
)
from mcp_google_workspace.tools.sheets.manage import (
    copy_sheet,
    create_sheet,
    create_spreadsheet,
    delete_sheet,
    duplicate_spreadsheet,
    list_sheets,
    move_spreadsheet,
    rename_sheet,
)
from mcp_google_workspace.tools.sheets.charts import add_chart


def _mock_ctx(sheets_service=None, drive_service=None, folder_id=None):
    """Build a mock Context with lifespan_context services."""
    ctx = MagicMock()
    lifespan = MagicMock()
    lifespan.sheets_service = sheets_service or MagicMock()
    lifespan.drive_service = drive_service or MagicMock()
    lifespan.folder_id = folder_id
    ctx.request_context.lifespan_context = lifespan
    return ctx


class TestGetSheetData:
    """Tests for get_sheet_data."""

    def test_basic_read(self):
        svc = MagicMock()
        svc.spreadsheets().values().get().execute.return_value = {
            "values": [["A", "B"], [1, 2]],
        }
        ctx = _mock_ctx(sheets_service=svc)

        result = get_sheet_data("sid", "Sheet1", ctx=ctx)
        assert "valueRanges" in result
        assert result["valueRanges"][0]["range"] == "Sheet1"

    def test_read_with_range(self):
        svc = MagicMock()
        svc.spreadsheets().values().get().execute.return_value = {
            "values": [[1, 2]],
        }
        ctx = _mock_ctx(sheets_service=svc)

        result = get_sheet_data("sid", "Sheet1", range="A1:B1", ctx=ctx)
        assert result["valueRanges"][0]["range"] == "Sheet1!A1:B1"


class TestGetSheetFormulas:
    """Tests for get_sheet_formulas."""

    def test_returns_formulas(self):
        svc = MagicMock()
        svc.spreadsheets().values().get().execute.return_value = {
            "values": [["=SUM(A1:A10)"]],
        }
        ctx = _mock_ctx(sheets_service=svc)

        result = get_sheet_formulas("sid", "Sheet1", ctx=ctx)
        assert result == [["=SUM(A1:A10)"]]


class TestUpdateCells:
    """Tests for update_cells."""

    def test_write_data(self):
        svc = MagicMock()
        svc.spreadsheets().values().update().execute.return_value = {
            "updatedCells": 4,
        }
        ctx = _mock_ctx(sheets_service=svc)

        result = update_cells("sid", "Sheet1", "A1:B2", [[1, 2], [3, 4]], ctx=ctx)
        assert result["updatedCells"] == 4


class TestAppendRows:
    """Tests for append_rows."""

    def test_append_data(self):
        svc = MagicMock()
        svc.spreadsheets().values().append().execute.return_value = {
            "updates": {"updatedRows": 2},
        }
        ctx = _mock_ctx(sheets_service=svc)

        result = append_rows("sid", "Sheet1", [["a", "b"], ["c", "d"]], ctx=ctx)
        assert "updates" in result


class TestClearRange:
    """Tests for clear_range."""

    def test_clear(self):
        svc = MagicMock()
        svc.spreadsheets().values().clear().execute.return_value = {
            "clearedRange": "Sheet1!A1:C10",
        }
        ctx = _mock_ctx(sheets_service=svc)

        result = clear_range("sid", "Sheet1", "A1:C10", ctx=ctx)
        assert result["clearedRange"] == "Sheet1!A1:C10"


class TestDeleteRows:
    """Tests for delete_rows."""

    def test_sheet_not_found(self):
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "sheets": [],
        }
        ctx = _mock_ctx(sheets_service=svc)

        result = delete_rows("sid", "Missing", 0, 1, ctx=ctx)
        assert "error" in result

    def test_delete_success(self):
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "sheets": [{"properties": {"title": "Sheet1", "sheetId": 0}}],
        }
        svc.spreadsheets().batchUpdate().execute.return_value = {"replies": []}
        ctx = _mock_ctx(sheets_service=svc)

        result = delete_rows("sid", "Sheet1", 0, 2, ctx=ctx)
        assert "error" not in result


class TestDeleteColumns:
    """Tests for delete_columns."""

    def test_sheet_not_found(self):
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "sheets": [],
        }
        ctx = _mock_ctx(sheets_service=svc)

        result = delete_columns("sid", "Missing", 0, 1, ctx=ctx)
        assert "error" in result


class TestCreateSpreadsheet:
    """Tests for create_spreadsheet."""

    def test_creates_with_title(self):
        drive = MagicMock()
        drive.files().create().execute.return_value = {
            "id": "new_id",
            "name": "Test Sheet",
            "parents": ["folder123"],
        }
        ctx = _mock_ctx(drive_service=drive)

        result = create_spreadsheet("Test Sheet", ctx=ctx)
        assert result["spreadsheetId"] == "new_id"
        assert result["title"] == "Test Sheet"


class TestCreateSheet:
    """Tests for create_sheet."""

    def test_creates_tab(self):
        svc = MagicMock()
        svc.spreadsheets().batchUpdate().execute.return_value = {
            "replies": [
                {
                    "addSheet": {
                        "properties": {
                            "sheetId": 123,
                            "title": "NewTab",
                            "index": 1,
                        }
                    }
                }
            ]
        }
        ctx = _mock_ctx(sheets_service=svc)

        result = create_sheet("sid", "NewTab", ctx=ctx)
        assert result["sheetId"] == 123
        assert result["title"] == "NewTab"


class TestDeleteSheet:
    """Tests for delete_sheet."""

    def test_sheet_not_found(self):
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "sheets": [],
        }
        ctx = _mock_ctx(sheets_service=svc)

        result = delete_sheet("sid", "Missing", ctx=ctx)
        assert "error" in result

    def test_delete_success(self):
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "sheets": [{"properties": {"title": "Sheet1", "sheetId": 0}}],
        }
        svc.spreadsheets().batchUpdate().execute.return_value = {"replies": []}
        ctx = _mock_ctx(sheets_service=svc)

        result = delete_sheet("sid", "Sheet1", ctx=ctx)
        assert "error" not in result


class TestListSheets:
    """Tests for list_sheets."""

    def test_returns_names(self):
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "sheets": [
                {"properties": {"title": "Sheet1"}},
                {"properties": {"title": "Sheet2"}},
            ]
        }
        ctx = _mock_ctx(sheets_service=svc)

        result = list_sheets("sid", ctx=ctx)
        assert result == ["Sheet1", "Sheet2"]


class TestRenameSheet:
    """Tests for rename_sheet."""

    def test_sheet_not_found(self):
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "sheets": [],
        }
        ctx = _mock_ctx(sheets_service=svc)

        result = rename_sheet("sid", "Missing", "NewName", ctx=ctx)
        assert "error" in result


class TestFindInSpreadsheet:
    """Tests for find_in_spreadsheet."""

    def test_finds_matching_cells(self):
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "sheets": [{"properties": {"title": "Sheet1", "sheetId": 0}}],
        }
        svc.spreadsheets().values().get().execute.return_value = {
            "values": [["hello", "world"], ["foo", "hello bar"]],
        }
        ctx = _mock_ctx(sheets_service=svc)

        results = find_in_spreadsheet("sid", "hello", ctx=ctx)
        assert len(results) == 2
        assert results[0]["cell"] == "A1"
        assert results[1]["cell"] == "B2"

    def test_case_insensitive(self):
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "sheets": [{"properties": {"title": "Sheet1", "sheetId": 0}}],
        }
        svc.spreadsheets().values().get().execute.return_value = {
            "values": [["Hello", "HELLO"]],
        }
        ctx = _mock_ctx(sheets_service=svc)

        results = find_in_spreadsheet("sid", "hello", case_sensitive=False, ctx=ctx)
        assert len(results) == 2

    def test_sheet_not_found(self):
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "sheets": [],
        }
        ctx = _mock_ctx(sheets_service=svc)

        result = find_in_spreadsheet("sid", "query", sheet="Missing", ctx=ctx)
        assert "error" in result

    def test_max_results(self):
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "sheets": [{"properties": {"title": "Sheet1", "sheetId": 0}}],
        }
        svc.spreadsheets().values().get().execute.return_value = {
            "values": [["x"] * 10],
        }
        ctx = _mock_ctx(sheets_service=svc)

        results = find_in_spreadsheet("sid", "x", max_results=3, ctx=ctx)
        assert len(results) == 3


class TestCopySheet:
    """Tests for copy_sheet."""

    def test_source_not_found(self):
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {"sheets": []}
        ctx = _mock_ctx(sheets_service=svc)

        result = copy_sheet("src_id", "Missing", "dst_id", "NewName", ctx=ctx)
        assert "error" in result

    def test_copy_with_rename(self):
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "sheets": [{"properties": {"title": "Sheet1", "sheetId": 0}}],
        }
        svc.spreadsheets().sheets().copyTo().execute.return_value = {
            "sheetId": 99,
            "title": "Copy of Sheet1",
        }
        svc.spreadsheets().batchUpdate().execute.return_value = {"replies": []}
        ctx = _mock_ctx(sheets_service=svc)

        result = copy_sheet("src_id", "Sheet1", "dst_id", "Renamed", ctx=ctx)
        assert "copy" in result
        assert "rename" in result

    def test_copy_without_rename(self):
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "sheets": [{"properties": {"title": "Sheet1", "sheetId": 0}}],
        }
        svc.spreadsheets().sheets().copyTo().execute.return_value = {
            "sheetId": 99,
            "title": "SameName",
        }
        ctx = _mock_ctx(sheets_service=svc)

        result = copy_sheet("src_id", "Sheet1", "dst_id", "SameName", ctx=ctx)
        assert "copy" in result
        assert "rename" not in result


class TestDuplicateSpreadsheet:
    """Tests for duplicate_spreadsheet."""

    def test_duplicates_with_title(self):
        drive = MagicMock()
        drive.files().copy().execute.return_value = {
            "id": "copy_id",
            "name": "Copy of Report",
            "parents": ["folder123"],
        }
        ctx = _mock_ctx(drive_service=drive)

        result = duplicate_spreadsheet("orig_id", new_title="Copy of Report", ctx=ctx)
        assert result["spreadsheetId"] == "copy_id"
        assert result["title"] == "Copy of Report"
        assert result["folder"] == "folder123"

    def test_duplicates_without_title(self):
        drive = MagicMock()
        drive.files().copy().execute.return_value = {
            "id": "copy_id",
            "name": "Original",
            "parents": [],
        }
        ctx = _mock_ctx(drive_service=drive)

        result = duplicate_spreadsheet("orig_id", ctx=ctx)
        assert result["spreadsheetId"] == "copy_id"
        assert result["folder"] == "root"


class TestMoveSpreadsheet:
    """Tests for move_spreadsheet."""

    def test_moves_to_folder(self):
        drive = MagicMock()
        drive.files().get().execute.return_value = {"parents": ["old_folder"]}
        drive.files().update().execute.return_value = {
            "id": "sid",
            "name": "My Sheet",
            "parents": ["new_folder"],
        }
        ctx = _mock_ctx(drive_service=drive)

        result = move_spreadsheet("sid", "new_folder", ctx=ctx)
        assert result["spreadsheetId"] == "sid"
        assert result["folder"] == "new_folder"

    def test_moves_from_root(self):
        drive = MagicMock()
        drive.files().get().execute.return_value = {"parents": []}
        drive.files().update().execute.return_value = {
            "id": "sid",
            "name": "My Sheet",
            "parents": ["target_folder"],
        }
        ctx = _mock_ctx(drive_service=drive)

        result = move_spreadsheet("sid", "target_folder", ctx=ctx)
        assert result["folder"] == "target_folder"


class TestAddChart:
    """Tests for add_chart."""

    def test_invalid_chart_type(self):
        ctx = _mock_ctx()
        result = add_chart("sid", "Sheet1", "INVALID", "A1:B5", ctx=ctx)
        assert "error" in result
        assert "Invalid chart type" in result["error"]

    def test_sheet_not_found(self):
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {"sheets": []}
        ctx = _mock_ctx(sheets_service=svc)

        result = add_chart("sid", "Missing", "LINE", "A1:B5", ctx=ctx)
        assert "error" in result
        assert "not found" in result["error"]

    def test_creates_basic_chart(self):
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "sheets": [{"properties": {"title": "Sheet1", "sheetId": 0}}],
        }
        svc.spreadsheets().batchUpdate().execute.return_value = {
            "replies": [{"addChart": {"chart": {"chartId": 42}}}],
        }
        ctx = _mock_ctx(sheets_service=svc)

        result = add_chart("sid", "Sheet1", "LINE", "A1:B10", title="Revenue", ctx=ctx)
        assert result["success"] is True
        assert result["chartId"] == 42

    def test_creates_pie_chart(self):
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "sheets": [{"properties": {"title": "Sheet1", "sheetId": 0}}],
        }
        svc.spreadsheets().batchUpdate().execute.return_value = {
            "replies": [{"addChart": {"chart": {"chartId": 7}}}],
        }
        ctx = _mock_ctx(sheets_service=svc)

        result = add_chart("sid", "Sheet1", "PIE", "A1:B5", ctx=ctx)
        assert result["success"] is True
        assert result["chartId"] == 7

    def test_invalid_range(self):
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "sheets": [{"properties": {"title": "Sheet1", "sheetId": 0}}],
        }
        ctx = _mock_ctx(sheets_service=svc)

        result = add_chart("sid", "Sheet1", "BAR", "INVALID!!!", ctx=ctx)
        assert "error" in result

    def test_api_failure(self):
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "sheets": [{"properties": {"title": "Sheet1", "sheetId": 0}}],
        }
        svc.spreadsheets().batchUpdate().execute.side_effect = HttpError(httplib2.Response({"status": 500}), b"API error")
        ctx = _mock_ctx(sheets_service=svc)

        result = add_chart("sid", "Sheet1", "COLUMN", "A1:C10", ctx=ctx)
        assert "error" in result
        assert "Failed to add chart" in result["error"]
