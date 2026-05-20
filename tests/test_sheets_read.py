"""Tests for Google Sheets read operations."""

from unittest.mock import MagicMock

import httplib2
from googleapiclient.errors import HttpError

from mcp_google_workspace.tools.sheets.read import (
    find_in_spreadsheet,
    get_multiple_sheet_data,
    get_multiple_spreadsheet_summary,
    get_sheet_data,
    get_sheet_formulas,
)


def _mock_ctx(sheets_service=None):
    ctx = MagicMock()
    lifespan = MagicMock()
    lifespan.sheets_service = sheets_service or MagicMock()
    ctx.request_context.lifespan_context = lifespan
    return ctx


# ---------------------------------------------------------------------------
# get_sheet_data
# ---------------------------------------------------------------------------


class TestGetSheetData:

    def test_returns_values_without_range(self):
        svc = MagicMock()
        svc.spreadsheets().values().get().execute.return_value = {
            "values": [["a", "b"]],
        }
        result = get_sheet_data("sid", "Sheet1", ctx=_mock_ctx(svc))
        assert result["valueRanges"][0]["range"] == "Sheet1"
        assert result["valueRanges"][0]["values"] == [["a", "b"]]

    def test_returns_values_with_range(self):
        svc = MagicMock()
        svc.spreadsheets().values().get().execute.return_value = {"values": [[1]]}
        result = get_sheet_data("sid", "S", range="A1:B2", ctx=_mock_ctx(svc))
        assert result["valueRanges"][0]["range"] == "S!A1:B2"

    def test_include_grid_data(self):
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {"sheets": []}
        result = get_sheet_data(
            "sid", "S", include_grid_data=True, ctx=_mock_ctx(svc)
        )
        assert result == {"sheets": []}

    def test_empty_values(self):
        svc = MagicMock()
        svc.spreadsheets().values().get().execute.return_value = {}
        result = get_sheet_data("sid", "S", ctx=_mock_ctx(svc))
        assert result["valueRanges"][0]["values"] == []


# ---------------------------------------------------------------------------
# get_sheet_formulas
# ---------------------------------------------------------------------------


class TestGetSheetFormulas:

    def test_returns_formulas(self):
        svc = MagicMock()
        svc.spreadsheets().values().get().execute.return_value = {
            "values": [["=SUM(A1:A5)"]],
        }
        result = get_sheet_formulas("sid", "S", ctx=_mock_ctx(svc))
        assert result == [["=SUM(A1:A5)"]]

    def test_empty_sheet(self):
        svc = MagicMock()
        svc.spreadsheets().values().get().execute.return_value = {}
        result = get_sheet_formulas("sid", "S", ctx=_mock_ctx(svc))
        assert result == []

    def test_with_range(self):
        svc = MagicMock()
        svc.spreadsheets().values().get().execute.return_value = {
            "values": [["=A1+B1"]],
        }
        result = get_sheet_formulas("sid", "S", range="C1", ctx=_mock_ctx(svc))
        assert result == [["=A1+B1"]]


# ---------------------------------------------------------------------------
# get_multiple_sheet_data
# ---------------------------------------------------------------------------


class TestGetMultipleSheetData:

    def test_valid_queries(self):
        svc = MagicMock()
        svc.spreadsheets().values().get().execute.return_value = {
            "values": [["x"]],
        }
        queries = [
            {"spreadsheet_id": "s1", "sheet": "S1"},
            {"spreadsheet_id": "s2", "sheet": "S2", "range": "A1:B2"},
        ]
        result = get_multiple_sheet_data(queries, ctx=_mock_ctx(svc))
        assert len(result) == 2
        assert result[0]["data"] == [["x"]]
        assert result[1]["data"] == [["x"]]

    def test_missing_required_keys(self):
        result = get_multiple_sheet_data(
            [{"spreadsheet_id": "s1"}], ctx=_mock_ctx()
        )
        assert "error" in result[0]
        assert "Missing required" in result[0]["error"]

    def test_api_error_captured(self):
        svc = MagicMock()
        svc.spreadsheets().values().get().execute.side_effect = HttpError(httplib2.Response({"status": 500}), b"boom")
        result = get_multiple_sheet_data(
            [{"spreadsheet_id": "s1", "sheet": "S"}], ctx=_mock_ctx(svc)
        )
        assert "error" in result[0]
        assert "boom" in result[0]["error"]

    def test_empty_queries_list(self):
        result = get_multiple_sheet_data([], ctx=_mock_ctx())
        assert result == []


# ---------------------------------------------------------------------------
# get_multiple_spreadsheet_summary
# ---------------------------------------------------------------------------


class TestGetMultipleSpreadsheetSummary:

    def test_basic_summary(self):
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "properties": {"title": "My Sheet"},
            "sheets": [
                {"properties": {"title": "Tab1", "sheetId": 0}},
            ],
        }
        svc.spreadsheets().values().get().execute.return_value = {
            "values": [["H1", "H2"], ["r1", "r2"]],
        }
        result = get_multiple_spreadsheet_summary(["sid"], ctx=_mock_ctx(svc))
        assert len(result) == 1
        assert result[0]["title"] == "My Sheet"
        assert result[0]["sheets"][0]["headers"] == ["H1", "H2"]
        assert result[0]["sheets"][0]["first_rows"] == [["r1", "r2"]]

    def test_spreadsheet_error(self):
        svc = MagicMock()
        svc.spreadsheets().get().execute.side_effect = HttpError(httplib2.Response({"status": 404}), b"not found")
        result = get_multiple_spreadsheet_summary(["bad"], ctx=_mock_ctx(svc))
        assert result[0]["error"] is not None
        assert "not found" in result[0]["error"]

    def test_sheet_data_error(self):
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "properties": {"title": "T"},
            "sheets": [{"properties": {"title": "S", "sheetId": 0}}],
        }
        svc.spreadsheets().values().get().execute.side_effect = HttpError(httplib2.Response({"status": 403}), b"denied")
        result = get_multiple_spreadsheet_summary(["sid"], ctx=_mock_ctx(svc))
        assert result[0]["sheets"][0]["error"] is not None

    def test_empty_sheet(self):
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "properties": {"title": "T"},
            "sheets": [{"properties": {"title": "S", "sheetId": 0}}],
        }
        svc.spreadsheets().values().get().execute.return_value = {"values": []}
        result = get_multiple_spreadsheet_summary(["sid"], ctx=_mock_ctx(svc))
        assert result[0]["sheets"][0]["headers"] == []

    def test_missing_sheet_title(self):
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "properties": {"title": "T"},
            "sheets": [{"properties": {"sheetId": 0}}],
        }
        result = get_multiple_spreadsheet_summary(["sid"], ctx=_mock_ctx(svc))
        assert result[0]["sheets"][0]["error"] is not None


# ---------------------------------------------------------------------------
# find_in_spreadsheet
# ---------------------------------------------------------------------------


class TestFindInSpreadsheet:

    def test_finds_matching_cells(self):
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "sheets": [{"properties": {"title": "S1"}}],
        }
        svc.spreadsheets().values().get().execute.return_value = {
            "values": [["hello", "world"], ["foo", "hello again"]],
        }
        result = find_in_spreadsheet("sid", "hello", ctx=_mock_ctx(svc))
        assert len(result) == 2
        assert result[0]["cell"] == "A1"
        assert result[1]["cell"] == "B2"

    def test_case_insensitive_search(self):
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "sheets": [{"properties": {"title": "S"}}],
        }
        svc.spreadsheets().values().get().execute.return_value = {
            "values": [["HELLO"]],
        }
        result = find_in_spreadsheet(
            "sid", "hello", case_sensitive=False, ctx=_mock_ctx(svc)
        )
        assert len(result) == 1

    def test_case_sensitive_search_no_match(self):
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "sheets": [{"properties": {"title": "S"}}],
        }
        svc.spreadsheets().values().get().execute.return_value = {
            "values": [["HELLO"]],
        }
        result = find_in_spreadsheet(
            "sid", "hello", case_sensitive=True, ctx=_mock_ctx(svc)
        )
        assert len(result) == 0

    def test_sheet_not_found(self):
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "sheets": [{"properties": {"title": "Other"}}],
        }
        result = find_in_spreadsheet(
            "sid", "q", sheet="Missing", ctx=_mock_ctx(svc)
        )
        assert "error" in result

    def test_max_results_limit(self):
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "sheets": [{"properties": {"title": "S"}}],
        }
        svc.spreadsheets().values().get().execute.return_value = {
            "values": [["a", "a", "a"], ["a", "a", "a"]],
        }
        result = find_in_spreadsheet(
            "sid", "a", max_results=3, ctx=_mock_ctx(svc)
        )
        assert len(result) == 3

    def test_filter_by_specific_sheet(self):
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "sheets": [
                {"properties": {"title": "S1"}},
                {"properties": {"title": "S2"}},
            ],
        }
        svc.spreadsheets().values().get().execute.return_value = {
            "values": [["match"]],
        }
        result = find_in_spreadsheet(
            "sid", "match", sheet="S1", ctx=_mock_ctx(svc)
        )
        assert len(result) == 1
        assert result[0]["sheet"] == "S1"

    # --- match_type tests ---

    def test_match_type_exact(self):
        """exact: only full cell value matches, not substrings."""
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "sheets": [{"properties": {"title": "S"}}],
        }
        svc.spreadsheets().values().get().execute.return_value = {
            "values": [["hello", "hello world", "HELLO"]],
        }
        result = find_in_spreadsheet(
            "sid", "hello", match_type="exact", ctx=_mock_ctx(svc)
        )
        # "hello" exact (case-insensitive default), "HELLO" also matches
        assert len(result) == 2
        assert result[0]["value"] == "hello"
        assert result[1]["value"] == "HELLO"

    def test_match_type_exact_case_sensitive(self):
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "sheets": [{"properties": {"title": "S"}}],
        }
        svc.spreadsheets().values().get().execute.return_value = {
            "values": [["hello", "Hello", "HELLO"]],
        }
        result = find_in_spreadsheet(
            "sid", "hello", match_type="exact", case_sensitive=True,
            ctx=_mock_ctx(svc),
        )
        assert len(result) == 1
        assert result[0]["value"] == "hello"

    def test_match_type_starts_with(self):
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "sheets": [{"properties": {"title": "S"}}],
        }
        svc.spreadsheets().values().get().execute.return_value = {
            "values": [["hello world", "world hello", "HELLO there"]],
        }
        result = find_in_spreadsheet(
            "sid", "hello", match_type="starts_with", ctx=_mock_ctx(svc)
        )
        # "hello world" and "HELLO there" start with hello (case-insensitive)
        assert len(result) == 2

    def test_match_type_regex(self):
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "sheets": [{"properties": {"title": "S"}}],
        }
        svc.spreadsheets().values().get().execute.return_value = {
            "values": [["abc-123", "xyz-456", "abc", "123"]],
        }
        result = find_in_spreadsheet(
            "sid", r"^[a-z]+-\d+$", match_type="regex", ctx=_mock_ctx(svc)
        )
        assert len(result) == 2
        assert result[0]["value"] == "abc-123"
        assert result[1]["value"] == "xyz-456"

    def test_match_type_regex_invalid_pattern(self):
        """Invalid regex should return error, not crash."""
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "sheets": [{"properties": {"title": "S"}}],
        }
        result = find_in_spreadsheet(
            "sid", "[invalid(", match_type="regex", ctx=_mock_ctx(svc)
        )
        assert "error" in result

    def test_match_type_invalid_value(self):
        """Unknown match_type should return error."""
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "sheets": [{"properties": {"title": "S"}}],
        }
        result = find_in_spreadsheet(
            "sid", "test", match_type="fuzzy", ctx=_mock_ctx(svc)
        )
        assert "error" in result

    # --- columns filter tests ---

    def test_columns_filter_by_header_name(self):
        """Only search in specified columns identified by header name."""
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "sheets": [{"properties": {"title": "S"}}],
        }
        svc.spreadsheets().values().get().execute.return_value = {
            "values": [
                ["Name", "Email", "City"],
                ["Alice", "alice@test.com", "Tokyo"],
                ["Bob", "bob@test.com", "Alice Springs"],
            ],
        }
        result = find_in_spreadsheet(
            "sid", "Alice", columns=["Name"], ctx=_mock_ctx(svc)
        )
        # Only "Alice" in Name column, not "Alice Springs" in City
        assert len(result) == 1
        assert result[0]["cell"] == "A2"

    def test_columns_filter_multiple(self):
        """Search across multiple specified columns."""
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "sheets": [{"properties": {"title": "S"}}],
        }
        svc.spreadsheets().values().get().execute.return_value = {
            "values": [
                ["Name", "Email", "City"],
                ["test", "test@x.com", "Tokyo"],
                ["Bob", "bob@test.com", "test city"],
            ],
        }
        result = find_in_spreadsheet(
            "sid", "test", columns=["Name", "Email"], ctx=_mock_ctx(svc)
        )
        # row1: "test" in Name, "test@x.com" in Email
        # row2: "bob@test.com" in Email
        # "test city" in City excluded
        assert len(result) == 3

    def test_columns_filter_nonexistent_header(self):
        """Non-existent column header is silently ignored."""
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "sheets": [{"properties": {"title": "S"}}],
        }
        svc.spreadsheets().values().get().execute.return_value = {
            "values": [
                ["Name", "Email"],
                ["test", "test@x.com"],
            ],
        }
        result = find_in_spreadsheet(
            "sid", "test", columns=["NonExistent"], ctx=_mock_ctx(svc)
        )
        assert len(result) == 0

    # --- include_row_context tests ---

    def test_include_row_context(self):
        """When include_row_context=True, result includes headers and full row."""
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "sheets": [{"properties": {"title": "S"}}],
        }
        svc.spreadsheets().values().get().execute.return_value = {
            "values": [
                ["Name", "Email", "City"],
                ["Alice", "bob@test.com", "Tokyo"],
            ],
        }
        result = find_in_spreadsheet(
            "sid", "Alice", include_row_context=True, ctx=_mock_ctx(svc)
        )
        assert len(result) == 1
        assert result[0]["row_data"] == {
            "Name": "Alice",
            "Email": "bob@test.com",
            "City": "Tokyo",
        }

    def test_no_row_context_by_default(self):
        """By default, result should NOT include row_data."""
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "sheets": [{"properties": {"title": "S"}}],
        }
        svc.spreadsheets().values().get().execute.return_value = {
            "values": [
                ["Name", "Email"],
                ["Alice", "bob@test.com"],
            ],
        }
        result = find_in_spreadsheet(
            "sid", "Alice", ctx=_mock_ctx(svc)
        )
        assert len(result) == 1
        assert "row_data" not in result[0]

    def test_row_context_with_missing_columns(self):
        """Row context handles rows shorter than headers gracefully."""
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "sheets": [{"properties": {"title": "S"}}],
        }
        svc.spreadsheets().values().get().execute.return_value = {
            "values": [
                ["Name", "Email", "City"],
                ["Alice"],  # shorter than headers
            ],
        }
        result = find_in_spreadsheet(
            "sid", "Alice", include_row_context=True, ctx=_mock_ctx(svc)
        )
        assert len(result) == 1
        assert result[0]["row_data"] == {
            "Name": "Alice",
            "Email": "",
            "City": "",
        }
