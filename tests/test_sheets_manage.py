"""Tests for Google Sheets management operations (search, list, etc.)."""

from unittest.mock import MagicMock

from mcp_google_workspace.tools.sheets.manage import search_spreadsheets


def _mock_ctx(drive_service=None, folder_id=None):
    """Build a mock Context with lifespan_context services."""
    ctx = MagicMock()
    lifespan = MagicMock()
    lifespan.drive_service = drive_service or MagicMock()
    lifespan.folder_id = folder_id
    ctx.request_context.lifespan_context = lifespan
    return ctx


class TestSearchSpreadsheets:
    """Tests for search_spreadsheets with pagination and folder filter."""

    def _drive_with_response(self, files, next_page_token=None):
        """Build mock drive returning files list with optional nextPageToken."""
        drive = MagicMock()
        response = {"files": files}
        if next_page_token:
            response["nextPageToken"] = next_page_token
        drive.files().list().execute.return_value = response
        return drive

    def _sample_files(self):
        return [
            {
                "id": "ss_a",
                "name": "Budget 2025",
                "createdTime": "2025-01-01T00:00:00Z",
                "modifiedTime": "2025-06-01T00:00:00Z",
                "owners": [{"emailAddress": "alice@example.com"}],
                "webViewLink": "https://docs.google.com/spreadsheets/d/ss_a",
            },
        ]

    def test_returns_dict_with_items(self):
        """Return type should be dict with 'items' key."""
        drive = self._drive_with_response(self._sample_files())
        ctx = _mock_ctx(drive_service=drive)

        result = search_spreadsheets("Budget", ctx=ctx)

        assert isinstance(result, dict)
        assert "items" in result
        assert len(result["items"]) == 1
        assert result["items"][0]["id"] == "ss_a"
        assert result["items"][0]["name"] == "Budget 2025"
        assert result["items"][0]["owners"] == ["alice@example.com"]

    def test_next_page_token_returned(self):
        """When Drive API returns nextPageToken, include it in response."""
        drive = self._drive_with_response(
            self._sample_files(), next_page_token="token_page2"
        )
        ctx = _mock_ctx(drive_service=drive)

        result = search_spreadsheets("Budget", ctx=ctx)

        assert result["next_page_token"] == "token_page2"

    def test_no_next_page_token_when_exhausted(self):
        """When no more pages, next_page_token should be None."""
        drive = self._drive_with_response(self._sample_files())
        ctx = _mock_ctx(drive_service=drive)

        result = search_spreadsheets("Budget", ctx=ctx)

        assert result["next_page_token"] is None

    def test_page_token_forwarded_to_api(self):
        """page_token parameter should be passed to Drive API."""
        drive = self._drive_with_response([])
        ctx = _mock_ctx(drive_service=drive)

        search_spreadsheets("test", page_token="abc123", ctx=ctx)

        call_kwargs = drive.files().list.call_args[1]
        assert call_kwargs["pageToken"] == "abc123"

    def test_no_page_token_omitted_from_api(self):
        """When page_token is None, pageToken kwarg should not be sent."""
        drive = self._drive_with_response([])
        ctx = _mock_ctx(drive_service=drive)

        search_spreadsheets("test", ctx=ctx)

        call_kwargs = drive.files().list.call_args[1]
        assert "pageToken" not in call_kwargs

    def test_folder_id_filter(self):
        """When folder_id provided, Drive query includes parent filter."""
        drive = self._drive_with_response([])
        ctx = _mock_ctx(drive_service=drive)

        search_spreadsheets("test", folder_id="folder_abc", ctx=ctx)

        call_kwargs = drive.files().list.call_args[1]
        assert "folder_abc" in call_kwargs["q"]
        assert "in parents" in call_kwargs["q"]

    def test_query_uses_spreadsheet_mimetype(self):
        """Drive query must filter by Sheets mimeType."""
        drive = self._drive_with_response([])
        ctx = _mock_ctx(drive_service=drive)

        search_spreadsheets("test", ctx=ctx)

        call_kwargs = drive.files().list.call_args[1]
        assert "application/vnd.google-apps.spreadsheet" in call_kwargs["q"]

    def test_empty_results(self):
        """Returns empty items list when nothing matches."""
        drive = self._drive_with_response([])
        ctx = _mock_ctx(drive_service=drive)

        result = search_spreadsheets("nonexistent", ctx=ctx)

        assert result["items"] == []
        assert result["next_page_token"] is None

    def test_max_results_clamped(self):
        """max_results clamped between 1 and 100."""
        drive = self._drive_with_response([])
        ctx = _mock_ctx(drive_service=drive)

        search_spreadsheets("test", max_results=999, ctx=ctx)
        assert drive.files().list.call_args[1]["pageSize"] <= 100

        search_spreadsheets("test", max_results=-5, ctx=ctx)
        assert drive.files().list.call_args[1]["pageSize"] >= 1

    def test_empty_query_returns_error(self):
        """Empty query should return error without hitting API."""
        ctx = _mock_ctx()
        result = search_spreadsheets("", ctx=ctx)
        assert isinstance(result, dict)
        assert "error" in result

    def test_whitespace_only_query_returns_error(self):
        """Whitespace-only query should return error."""
        ctx = _mock_ctx()
        result = search_spreadsheets("   ", ctx=ctx)
        assert "error" in result

    def test_api_error_propagates(self):
        """API exception should propagate (not silently swallowed)."""
        drive = MagicMock()
        drive.files().list().execute.side_effect = Exception("Rate limit")
        ctx = _mock_ctx(drive_service=drive)

        try:
            search_spreadsheets("test", ctx=ctx)
            assert False, "Should have raised"
        except Exception as e:
            assert "Rate limit" in str(e)

    def test_query_escapes_special_chars(self):
        """Single quotes in query should be escaped."""
        drive = self._drive_with_response([])
        ctx = _mock_ctx(drive_service=drive)

        search_spreadsheets("O'Brien", ctx=ctx)

        query_str = drive.files().list.call_args[1]["q"]
        assert "O\\'Brien" in query_str
