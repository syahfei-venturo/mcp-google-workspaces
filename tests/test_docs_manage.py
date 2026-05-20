"""Tests for Google Docs management tools with mocked API services."""

from unittest.mock import MagicMock

from mcp_google_workspace.tools.docs.manage import (
    create_footer,
    create_header,
    create_named_range,
    delete_footer,
    delete_header,
    delete_named_range,
    search_documents,
)


def _mock_ctx(docs_service=None, drive_service=None, folder_id=None):
    """Build a mock Context with lifespan_context services."""
    ctx = MagicMock()
    lifespan = MagicMock()
    lifespan.docs_service = docs_service or MagicMock()
    lifespan.drive_service = drive_service or MagicMock()
    lifespan.folder_id = folder_id
    ctx.request_context.lifespan_context = lifespan
    return ctx


def _batch_ok():
    """Standard successful batchUpdate response."""
    return {"replies": []}


class TestCreateHeader:
    """Tests for create_header."""

    def test_creates_default_header(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = {
            "replies": [{"createHeader": {"headerId": "kix.hdr1"}}]
        }
        ctx = _mock_ctx(docs_service=svc)

        result = create_header("doc1", ctx=ctx)
        assert result["headerId"] == "kix.hdr1"
        assert result["sectionType"] == "DEFAULT"

    def test_creates_first_page_header(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = {
            "replies": [{"createHeader": {"headerId": "kix.hdr2"}}]
        }
        ctx = _mock_ctx(docs_service=svc)

        result = create_header("doc1", section_type="FIRST", ctx=ctx)
        assert result["sectionType"] == "FIRST"

    def test_invalid_section_type(self):
        ctx = _mock_ctx()
        result = create_header("doc1", section_type="INVALID", ctx=ctx)
        assert "error" in result

    def test_empty_document_id(self):
        ctx = _mock_ctx()
        result = create_header("", ctx=ctx)
        assert "error" in result

    def test_api_error_propagated(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.side_effect = Exception("API down")
        ctx = _mock_ctx(docs_service=svc)

        result = create_header("doc1", ctx=ctx)
        assert "error" in result


class TestCreateFooter:
    """Tests for create_footer."""

    def test_creates_default_footer(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = {
            "replies": [{"createFooter": {"footerId": "kix.ftr1"}}]
        }
        ctx = _mock_ctx(docs_service=svc)

        result = create_footer("doc1", ctx=ctx)
        assert result["footerId"] == "kix.ftr1"
        assert result["sectionType"] == "DEFAULT"

    def test_creates_first_page_footer(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = {
            "replies": [{"createFooter": {"footerId": "kix.ftr2"}}]
        }
        ctx = _mock_ctx(docs_service=svc)

        result = create_footer("doc1", section_type="FIRST", ctx=ctx)
        assert result["sectionType"] == "FIRST"

    def test_invalid_section_type(self):
        ctx = _mock_ctx()
        result = create_footer("doc1", section_type="LAST", ctx=ctx)
        assert "error" in result

    def test_empty_document_id(self):
        ctx = _mock_ctx()
        result = create_footer("", ctx=ctx)
        assert "error" in result


class TestDeleteHeader:
    """Tests for delete_header."""

    def test_deletes_header(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = delete_header("doc1", "kix.hdr1", ctx=ctx)
        assert result["deletedHeaderId"] == "kix.hdr1"

    def test_empty_document_id(self):
        ctx = _mock_ctx()
        result = delete_header("", "kix.hdr1", ctx=ctx)
        assert "error" in result

    def test_empty_header_id(self):
        ctx = _mock_ctx()
        result = delete_header("doc1", "", ctx=ctx)
        assert "error" in result


class TestDeleteFooter:
    """Tests for delete_footer."""

    def test_deletes_footer(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = delete_footer("doc1", "kix.ftr1", ctx=ctx)
        assert result["deletedFooterId"] == "kix.ftr1"

    def test_empty_document_id(self):
        ctx = _mock_ctx()
        result = delete_footer("", "kix.ftr1", ctx=ctx)
        assert "error" in result

    def test_empty_footer_id(self):
        ctx = _mock_ctx()
        result = delete_footer("doc1", "", ctx=ctx)
        assert "error" in result


class TestCreateNamedRange:
    """Tests for create_named_range."""

    def test_creates_range(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = {
            "replies": [{"createNamedRange": {"namedRangeId": "nr_abc"}}]
        }
        ctx = _mock_ctx(docs_service=svc)

        result = create_named_range(
            "doc1", name="intro", start_index=1, end_index=50, ctx=ctx
        )
        assert result["namedRangeId"] == "nr_abc"
        assert result["name"] == "intro"
        assert result["range"] == {"startIndex": 1, "endIndex": 50}

    def test_invalid_range(self):
        ctx = _mock_ctx()
        result = create_named_range(
            "doc1", name="test", start_index=50, end_index=10, ctx=ctx
        )
        assert "error" in result

    def test_empty_name(self):
        ctx = _mock_ctx()
        result = create_named_range(
            "doc1", name="", start_index=1, end_index=10, ctx=ctx
        )
        assert "error" in result

    def test_empty_document_id(self):
        ctx = _mock_ctx()
        result = create_named_range(
            "", name="test", start_index=1, end_index=10, ctx=ctx
        )
        assert "error" in result

    def test_name_too_long(self):
        ctx = _mock_ctx()
        result = create_named_range(
            "doc1", name="x" * 256, start_index=1, end_index=10, ctx=ctx
        )
        assert "error" in result
        assert "255" in result["error"]

    def test_api_error_propagated(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.side_effect = Exception("API down")
        ctx = _mock_ctx(docs_service=svc)

        result = create_named_range(
            "doc1", name="intro", start_index=1, end_index=50, ctx=ctx
        )
        assert "error" in result


class TestDeleteNamedRange:
    """Tests for delete_named_range."""

    def test_deletes_by_id(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = delete_named_range("doc1", named_range_id="nr_abc", ctx=ctx)
        assert result["deleted"] == "nr_abc"

    def test_deletes_by_name(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = delete_named_range("doc1", name="intro", ctx=ctx)
        assert result["deleted"] == "intro"

    def test_no_identifier_error(self):
        ctx = _mock_ctx()
        result = delete_named_range("doc1", ctx=ctx)
        assert "error" in result

    def test_empty_document_id(self):
        ctx = _mock_ctx()
        result = delete_named_range("", named_range_id="nr_abc", ctx=ctx)
        assert "error" in result


class TestSearchDocuments:
    """Tests for search_documents."""

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
                "id": "doc_a",
                "name": "Project Plan",
                "createdTime": "2025-01-10T00:00:00Z",
                "modifiedTime": "2025-06-01T00:00:00Z",
                "owners": [{"emailAddress": "alice@example.com"}],
                "webViewLink": "https://docs.google.com/document/d/doc_a",
            },
            {
                "id": "doc_b",
                "name": "Project Notes",
                "createdTime": "2025-02-15T00:00:00Z",
                "modifiedTime": "2025-05-20T00:00:00Z",
                "owners": [{"emailAddress": "bob@example.com"}],
                "webViewLink": "https://docs.google.com/document/d/doc_b",
            },
        ]

    def test_returns_dict_with_items(self):
        """Return type should be dict with 'items' key."""
        drive = self._drive_with_response(self._sample_files())
        ctx = _mock_ctx(drive_service=drive)

        result = search_documents("Project", ctx=ctx)

        assert isinstance(result, dict)
        assert "items" in result
        assert len(result["items"]) == 2
        assert result["items"][0]["id"] == "doc_a"
        assert result["items"][0]["name"] == "Project Plan"
        assert result["items"][0]["owners"] == ["alice@example.com"]
        assert result["items"][0]["web_link"] is not None

    def test_next_page_token_returned(self):
        """When Drive API returns nextPageToken, include it in response."""
        drive = self._drive_with_response(
            self._sample_files(), next_page_token="token_page2"
        )
        ctx = _mock_ctx(drive_service=drive)

        result = search_documents("Project", ctx=ctx)
        assert result["next_page_token"] == "token_page2"

    def test_no_next_page_token_when_exhausted(self):
        """When no more pages, next_page_token should be None."""
        drive = self._drive_with_response(self._sample_files())
        ctx = _mock_ctx(drive_service=drive)

        result = search_documents("Project", ctx=ctx)
        assert result["next_page_token"] is None

    def test_page_token_forwarded_to_api(self):
        """page_token parameter should be passed to Drive API."""
        drive = self._drive_with_response([])
        ctx = _mock_ctx(drive_service=drive)

        search_documents("test", page_token="abc123", ctx=ctx)

        call_kwargs = drive.files().list.call_args[1]
        assert call_kwargs["pageToken"] == "abc123"

    def test_no_page_token_omitted_from_api(self):
        """When page_token is None, pageToken kwarg should not be sent."""
        drive = self._drive_with_response([])
        ctx = _mock_ctx(drive_service=drive)

        search_documents("test", ctx=ctx)

        call_kwargs = drive.files().list.call_args[1]
        assert "pageToken" not in call_kwargs

    def test_empty_results(self):
        """Returns empty items list when no documents match."""
        drive = self._drive_with_response([])
        ctx = _mock_ctx(drive_service=drive)

        result = search_documents("nonexistent", ctx=ctx)
        assert result["items"] == []
        assert result["next_page_token"] is None

    def test_max_results_clamped_to_bounds(self):
        """max_results should be clamped between 1 and 100."""
        drive = self._drive_with_response([])
        ctx = _mock_ctx(drive_service=drive)

        search_documents("test", max_results=999, ctx=ctx)
        call_kwargs = drive.files().list.call_args
        assert call_kwargs[1]["pageSize"] <= 100

        search_documents("test", max_results=-5, ctx=ctx)
        call_kwargs = drive.files().list.call_args
        assert call_kwargs[1]["pageSize"] >= 1

    def test_folder_id_filter(self):
        """When folder_id is provided, the Drive query includes parent filter."""
        drive = self._drive_with_response([])
        ctx = _mock_ctx(drive_service=drive)

        search_documents("test", folder_id="folder_xyz", ctx=ctx)

        call_kwargs = drive.files().list.call_args
        query_str = call_kwargs[1]["q"]
        assert "folder_xyz" in query_str
        assert "in parents" in query_str

    def test_query_uses_document_mimetype(self):
        """Drive query must filter by Google Docs mimeType, not Sheets."""
        drive = self._drive_with_response([])
        ctx = _mock_ctx(drive_service=drive)

        search_documents("test", ctx=ctx)

        call_kwargs = drive.files().list.call_args
        query_str = call_kwargs[1]["q"]
        assert "application/vnd.google-apps.document" in query_str
        assert "spreadsheet" not in query_str

    def test_empty_query_returns_error(self):
        """Empty query should return error without hitting API."""
        ctx = _mock_ctx()
        result = search_documents("", ctx=ctx)
        assert isinstance(result, dict)
        assert "error" in result

    def test_whitespace_only_query_returns_error(self):
        """Whitespace-only query should return error."""
        ctx = _mock_ctx()
        result = search_documents("   ", ctx=ctx)
        assert "error" in result

    def test_api_error_propagates(self):
        """API exception should propagate (not silently swallowed)."""
        drive = MagicMock()
        drive.files().list().execute.side_effect = Exception("Forbidden")
        ctx = _mock_ctx(drive_service=drive)

        try:
            search_documents("test", ctx=ctx)
            assert False, "Should have raised"
        except Exception as e:
            assert "Forbidden" in str(e)

    def test_query_escapes_special_characters(self):
        """Single quotes in query should be escaped to prevent injection."""
        drive = self._drive_with_response([])
        ctx = _mock_ctx(drive_service=drive)

        search_documents("O'Brien's doc", ctx=ctx)

        call_kwargs = drive.files().list.call_args
        query_str = call_kwargs[1]["q"]
        assert "O\\'Brien\\'s doc" in query_str
