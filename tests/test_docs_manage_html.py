"""Tests for create_document_from_html."""

from unittest.mock import MagicMock, patch, call

from mcp_google_workspace.tools.docs.manage import (
    create_document_from_html,
    MAX_HTML_BYTES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_ctx(drive_service=None, folder_id=None):
    ctx = MagicMock()
    lifespan = MagicMock()
    lifespan.drive_service = drive_service or MagicMock()
    lifespan.folder_id = folder_id
    ctx.request_context.lifespan_context = lifespan
    return ctx


def _drive_create_ok(doc_id="doc_new", name="Test Doc", parents=None):
    """Build a mock drive service that returns a successful create response."""
    svc = MagicMock()
    response = {"id": doc_id, "name": name}
    if parents:
        response["parents"] = parents
    svc.files().create().execute.return_value = response
    return svc


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestCreateDocumentFromHtmlValidation:
    def test_empty_title(self):
        result = create_document_from_html("", "<p>hi</p>", ctx=_mock_ctx())
        assert "error" in result

    def test_whitespace_title(self):
        result = create_document_from_html("   ", "<p>hi</p>", ctx=_mock_ctx())
        assert "error" in result

    def test_empty_html_content(self):
        result = create_document_from_html("Title", "", ctx=_mock_ctx())
        assert "error" in result

    def test_whitespace_html_content(self):
        result = create_document_from_html("Title", "   \n  ", ctx=_mock_ctx())
        assert "error" in result

    def test_html_too_large(self):
        huge_html = "<p>" + "x" * (MAX_HTML_BYTES + 1) + "</p>"
        result = create_document_from_html("Title", huge_html, ctx=_mock_ctx())
        assert "error" in result
        assert "exceeds" in result["error"].lower() or "large" in result["error"].lower()


# ---------------------------------------------------------------------------
# Success cases
# ---------------------------------------------------------------------------


class TestCreateDocumentFromHtmlSuccess:
    def test_creates_document_returns_info(self):
        svc = _drive_create_ok(
            doc_id="doc_abc", name="Report", parents=["folder_1"]
        )
        ctx = _mock_ctx(drive_service=svc)

        result = create_document_from_html(
            "Report", "<h1>Hello</h1><p>World</p>", ctx=ctx
        )

        assert "error" not in result
        assert result["documentId"] == "doc_abc"
        assert result["title"] == "Report"
        assert result["folder"] == "folder_1"

    def test_uses_default_folder(self):
        svc = _drive_create_ok(parents=["default_folder"])
        ctx = _mock_ctx(drive_service=svc, folder_id="default_folder")

        create_document_from_html("Title", "<p>test</p>", ctx=ctx)

        # Verify the file body includes parent folder
        create_call = svc.files().create.call_args
        body = create_call.kwargs.get("body", create_call[1].get("body", {}))
        assert body["parents"] == ["default_folder"]

    def test_custom_folder_overrides_default(self):
        svc = _drive_create_ok(parents=["custom_folder"])
        ctx = _mock_ctx(drive_service=svc, folder_id="default_folder")

        create_document_from_html(
            "Title", "<p>test</p>", folder_id="custom_folder", ctx=ctx
        )

        create_call = svc.files().create.call_args
        body = create_call.kwargs.get("body", create_call[1].get("body", {}))
        assert body["parents"] == ["custom_folder"]

    def test_no_folder_omits_parents(self):
        svc = _drive_create_ok()
        ctx = _mock_ctx(drive_service=svc, folder_id=None)

        create_document_from_html("Title", "<p>test</p>", ctx=ctx)

        create_call = svc.files().create.call_args
        body = create_call.kwargs.get("body", create_call[1].get("body", {}))
        assert "parents" not in body

    def test_drive_api_called_with_correct_mimetypes(self):
        svc = _drive_create_ok()
        ctx = _mock_ctx(drive_service=svc)

        create_document_from_html("Title", "<p>test</p>", ctx=ctx)

        create_call = svc.files().create.call_args
        body = create_call.kwargs.get("body", create_call[1].get("body", {}))
        # Target mimeType must be Google Docs
        assert body["mimeType"] == "application/vnd.google-apps.document"

    def test_html_content_passed_as_media(self):
        """Verify MediaInMemoryUpload is used with text/html mimetype."""
        svc = _drive_create_ok()
        ctx = _mock_ctx(drive_service=svc)

        with patch(
            "mcp_google_workspace.tools.docs.manage.MediaInMemoryUpload"
        ) as mock_media:
            mock_media.return_value = MagicMock()
            create_document_from_html("Title", "<p>hello</p>", ctx=ctx)

            mock_media.assert_called_once()
            call_args = mock_media.call_args
            # First positional arg is the bytes
            html_bytes = call_args[0][0]
            assert html_bytes == b"<p>hello</p>"
            # mimetype kwarg
            assert call_args.kwargs.get("mimetype") == "text/html"

    def test_utf8_html_encoded_properly(self):
        """Non-ASCII HTML should be encoded as UTF-8."""
        svc = _drive_create_ok()
        ctx = _mock_ctx(drive_service=svc)

        html = "<p>日本語テスト</p>"
        with patch(
            "mcp_google_workspace.tools.docs.manage.MediaInMemoryUpload"
        ) as mock_media:
            mock_media.return_value = MagicMock()
            create_document_from_html("Title", html, ctx=ctx)

            html_bytes = mock_media.call_args[0][0]
            assert html_bytes == html.encode("utf-8")

    def test_root_folder_when_no_parents_in_response(self):
        svc = _drive_create_ok(parents=None)
        ctx = _mock_ctx(drive_service=svc)

        result = create_document_from_html("Title", "<p>test</p>", ctx=ctx)
        assert result["folder"] == "root"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestCreateDocumentFromHtmlErrors:
    def test_api_error_propagated(self):
        svc = MagicMock()
        svc.files().create().execute.side_effect = Exception("Quota exceeded")
        ctx = _mock_ctx(drive_service=svc)

        result = create_document_from_html("Title", "<p>test</p>", ctx=ctx)
        assert "error" in result
        assert "Quota exceeded" in result["error"]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestHtmlConstants:
    def test_max_html_bytes_reasonable(self):
        assert MAX_HTML_BYTES >= 100_000  # At least 100KB
        assert MAX_HTML_BYTES <= 10_000_000  # Not more than 10MB
