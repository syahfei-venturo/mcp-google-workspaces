"""Tests for Google Sheets write operations."""

from unittest.mock import MagicMock

from mcp_google_workspace.tools.sheets.write import (
    add_columns,
    add_rows,
    append_rows,
    batch_update,
    batch_update_cells,
    clear_range,
    delete_columns,
    delete_rows,
    merge_cells,
    sort_range,
    unmerge_cells,
    update_cells,
)


def _mock_ctx(sheets_service=None):
    ctx = MagicMock()
    lifespan = MagicMock()
    lifespan.sheets_service = sheets_service or MagicMock()
    ctx.request_context.lifespan_context = lifespan
    return ctx


def _svc_with_sheet_id(sheet_id=0):
    """Create a sheets service mock that returns a specific sheet ID."""
    svc = MagicMock()
    svc.spreadsheets().get().execute.return_value = {
        "sheets": [{"properties": {"title": "S", "sheetId": sheet_id}}],
    }
    svc.spreadsheets().batchUpdate().execute.return_value = {"replies": []}
    return svc


def _svc_no_sheet():
    """Create a sheets service mock where no sheet matches."""
    svc = MagicMock()
    svc.spreadsheets().get().execute.return_value = {
        "sheets": [{"properties": {"title": "Other", "sheetId": 0}}],
    }
    return svc


# ---------------------------------------------------------------------------
# update_cells
# ---------------------------------------------------------------------------


class TestUpdateCells:

    def test_writes_data(self):
        svc = MagicMock()
        svc.spreadsheets().values().update().execute.return_value = {
            "updatedCells": 4,
        }
        result = update_cells(
            "sid", "S", "A1:B2", [[1, 2], [3, 4]], ctx=_mock_ctx(svc)
        )
        assert result["updatedCells"] == 4


# ---------------------------------------------------------------------------
# batch_update_cells
# ---------------------------------------------------------------------------


class TestBatchUpdateCells:

    def test_batch_writes(self):
        svc = MagicMock()
        svc.spreadsheets().values().batchUpdate().execute.return_value = {
            "totalUpdatedCells": 6,
        }
        result = batch_update_cells(
            "sid", "S", {"A1:B2": [[1, 2]], "C1:D2": [[3, 4]]}, ctx=_mock_ctx(svc)
        )
        assert result["totalUpdatedCells"] == 6


# ---------------------------------------------------------------------------
# batch_update (raw)
# ---------------------------------------------------------------------------


class TestBatchUpdate:

    def test_executes_requests(self):
        svc = MagicMock()
        svc.spreadsheets().batchUpdate().execute.return_value = {"replies": [{}]}
        result = batch_update(
            "sid", [{"addSheet": {"properties": {"title": "New"}}}], ctx=_mock_ctx(svc)
        )
        assert "replies" in result

    def test_empty_requests_returns_error(self):
        result = batch_update("sid", [], ctx=_mock_ctx())
        assert "error" in result

    def test_invalid_request_type_returns_error(self):
        result = batch_update("sid", ["not_a_dict"], ctx=_mock_ctx())
        assert "error" in result


# ---------------------------------------------------------------------------
# add_rows
# ---------------------------------------------------------------------------


class TestAddRows:

    def test_inserts_rows(self):
        svc = _svc_with_sheet_id(42)
        result = add_rows("sid", "S", 5, ctx=_mock_ctx(svc))
        assert "replies" in result

    def test_inserts_at_position(self):
        svc = _svc_with_sheet_id(0)
        result = add_rows("sid", "S", 3, start_row=10, ctx=_mock_ctx(svc))
        assert "replies" in result

    def test_sheet_not_found(self):
        result = add_rows("sid", "Missing", 1, ctx=_mock_ctx(_svc_no_sheet()))
        assert "error" in result


# ---------------------------------------------------------------------------
# add_columns
# ---------------------------------------------------------------------------


class TestAddColumns:

    def test_inserts_columns(self):
        svc = _svc_with_sheet_id(0)
        result = add_columns("sid", "S", 3, ctx=_mock_ctx(svc))
        assert "replies" in result

    def test_sheet_not_found(self):
        result = add_columns("sid", "Missing", 1, ctx=_mock_ctx(_svc_no_sheet()))
        assert "error" in result


# ---------------------------------------------------------------------------
# append_rows
# ---------------------------------------------------------------------------


class TestAppendRows:

    def test_appends_data(self):
        svc = MagicMock()
        svc.spreadsheets().values().append().execute.return_value = {
            "updates": {"updatedRows": 2},
        }
        result = append_rows("sid", "S", [["a"], ["b"]], ctx=_mock_ctx(svc))
        assert result["updates"]["updatedRows"] == 2


# ---------------------------------------------------------------------------
# clear_range
# ---------------------------------------------------------------------------


class TestClearRange:

    def test_clears_cells(self):
        svc = MagicMock()
        svc.spreadsheets().values().clear().execute.return_value = {
            "clearedRange": "S!A1:B2",
        }
        result = clear_range("sid", "S", "A1:B2", ctx=_mock_ctx(svc))
        assert result["clearedRange"] == "S!A1:B2"


# ---------------------------------------------------------------------------
# delete_rows
# ---------------------------------------------------------------------------


class TestDeleteRows:

    def test_deletes_rows(self):
        svc = _svc_with_sheet_id(0)
        result = delete_rows("sid", "S", 0, 5, ctx=_mock_ctx(svc))
        assert "replies" in result

    def test_sheet_not_found(self):
        result = delete_rows("sid", "Missing", 0, 1, ctx=_mock_ctx(_svc_no_sheet()))
        assert "error" in result


# ---------------------------------------------------------------------------
# delete_columns
# ---------------------------------------------------------------------------


class TestDeleteColumns:

    def test_deletes_columns(self):
        svc = _svc_with_sheet_id(0)
        result = delete_columns("sid", "S", 0, 3, ctx=_mock_ctx(svc))
        assert "replies" in result

    def test_sheet_not_found(self):
        result = delete_columns(
            "sid", "Missing", 0, 1, ctx=_mock_ctx(_svc_no_sheet())
        )
        assert "error" in result


# ---------------------------------------------------------------------------
# sort_range
# ---------------------------------------------------------------------------


class TestSortRange:

    def test_sorts_ascending(self):
        svc = _svc_with_sheet_id(0)
        result = sort_range("sid", "S", "A1:C10", 0, ctx=_mock_ctx(svc))
        assert "replies" in result

    def test_sorts_descending(self):
        svc = _svc_with_sheet_id(0)
        result = sort_range(
            "sid", "S", "A1:C10", 1, ascending=False, ctx=_mock_ctx(svc)
        )
        assert "replies" in result

    def test_sheet_not_found(self):
        result = sort_range(
            "sid", "Missing", "A1:B2", 0, ctx=_mock_ctx(_svc_no_sheet())
        )
        assert "error" in result

    def test_invalid_range(self):
        svc = _svc_with_sheet_id(0)
        result = sort_range("sid", "S", "!!!bad", 0, ctx=_mock_ctx(svc))
        assert "error" in result


# ---------------------------------------------------------------------------
# merge_cells
# ---------------------------------------------------------------------------


class TestMergeCells:

    def test_merge_all(self):
        svc = _svc_with_sheet_id(0)
        result = merge_cells("sid", "S", "A1:C1", ctx=_mock_ctx(svc))
        assert "replies" in result

    def test_merge_rows(self):
        svc = _svc_with_sheet_id(0)
        result = merge_cells(
            "sid", "S", "A1:C3", merge_type="MERGE_ROWS", ctx=_mock_ctx(svc)
        )
        assert "replies" in result

    def test_invalid_merge_type(self):
        svc = _svc_with_sheet_id(0)
        result = merge_cells(
            "sid", "S", "A1:B2", merge_type="INVALID", ctx=_mock_ctx(svc)
        )
        assert "error" in result

    def test_sheet_not_found(self):
        result = merge_cells(
            "sid", "Missing", "A1:B2", ctx=_mock_ctx(_svc_no_sheet())
        )
        assert "error" in result

    def test_invalid_range(self):
        svc = _svc_with_sheet_id(0)
        result = merge_cells("sid", "S", "!!!bad", ctx=_mock_ctx(svc))
        assert "error" in result


# ---------------------------------------------------------------------------
# unmerge_cells
# ---------------------------------------------------------------------------


class TestUnmergeCells:

    def test_unmerge(self):
        svc = _svc_with_sheet_id(0)
        result = unmerge_cells("sid", "S", "A1:C1", ctx=_mock_ctx(svc))
        assert "replies" in result

    def test_sheet_not_found(self):
        result = unmerge_cells(
            "sid", "Missing", "A1:B2", ctx=_mock_ctx(_svc_no_sheet())
        )
        assert "error" in result

    def test_invalid_range(self):
        svc = _svc_with_sheet_id(0)
        result = unmerge_cells("sid", "S", "!!!bad", ctx=_mock_ctx(svc))
        assert "error" in result
