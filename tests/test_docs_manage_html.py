"""Tests for create_document (file_path based)."""

import os
import tempfile
from unittest.mock import MagicMock, patch

from mcp_google_workspace.tools.docs.manage import (
    create_document,
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


def _write_temp_html(content: str) -> str:
    """Write HTML content to a temp file and return the path."""
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".html", delete=False, encoding="utf-8"
    )
    f.write(content)
    f.close()
    return f.name


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestCreateDocumentValidation:
    def test_empty_title(self):
        path = _write_temp_html("<p>hi</p>")
        try:
            result = create_document("", path, ctx=_mock_ctx())
            assert "error" in result
        finally:
            os.unlink(path)

    def test_whitespace_title(self):
        path = _write_temp_html("<p>hi</p>")
        try:
            result = create_document("   ", path, ctx=_mock_ctx())
            assert "error" in result
        finally:
            os.unlink(path)

    def test_empty_file_path(self):
        result = create_document("Title", "", ctx=_mock_ctx())
        assert "error" in result

    def test_whitespace_file_path(self):
        result = create_document("Title", "   ", ctx=_mock_ctx())
        assert "error" in result

    def test_file_not_found(self):
        result = create_document("Title", "/nonexistent/file.html", ctx=_mock_ctx())
        assert "error" in result
        assert "not found" in result["error"].lower()

    def test_empty_html_file(self):
        path = _write_temp_html("   \n  ")
        try:
            result = create_document("Title", path, ctx=_mock_ctx())
            assert "error" in result
        finally:
            os.unlink(path)

    def test_html_too_large(self):
        huge_html = "<p>" + "x" * (MAX_HTML_BYTES + 1) + "</p>"
        path = _write_temp_html(huge_html)
        try:
            result = create_document("Title", path, ctx=_mock_ctx())
            assert "error" in result
            assert "exceeds" in result["error"].lower() or "large" in result["error"].lower()
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Success cases
# ---------------------------------------------------------------------------


class TestCreateDocumentSuccess:
    def test_creates_document_returns_info(self):
        svc = _drive_create_ok(
            doc_id="doc_abc", name="Report", parents=["folder_1"]
        )
        ctx = _mock_ctx(drive_service=svc)
        path = _write_temp_html("<h1>Hello</h1><p>World</p>")

        try:
            result = create_document("Report", path, ctx=ctx)

            assert "error" not in result
            assert result["documentId"] == "doc_abc"
            assert result["title"] == "Report"
            assert result["folder"] == "folder_1"
        finally:
            os.unlink(path)

    def test_uses_default_folder(self):
        svc = _drive_create_ok(parents=["default_folder"])
        ctx = _mock_ctx(drive_service=svc, folder_id="default_folder")
        path = _write_temp_html("<p>test</p>")

        try:
            create_document("Title", path, ctx=ctx)

            create_call = svc.files().create.call_args
            body = create_call.kwargs.get("body", create_call[1].get("body", {}))
            assert body["parents"] == ["default_folder"]
        finally:
            os.unlink(path)

    def test_custom_folder_overrides_default(self):
        svc = _drive_create_ok(parents=["custom_folder"])
        ctx = _mock_ctx(drive_service=svc, folder_id="default_folder")
        path = _write_temp_html("<p>test</p>")

        try:
            create_document(
                "Title", path, folder_id="custom_folder", ctx=ctx
            )

            create_call = svc.files().create.call_args
            body = create_call.kwargs.get("body", create_call[1].get("body", {}))
            assert body["parents"] == ["custom_folder"]
        finally:
            os.unlink(path)

    def test_no_folder_omits_parents(self):
        svc = _drive_create_ok()
        ctx = _mock_ctx(drive_service=svc, folder_id=None)
        path = _write_temp_html("<p>test</p>")

        try:
            create_document("Title", path, ctx=ctx)

            create_call = svc.files().create.call_args
            body = create_call.kwargs.get("body", create_call[1].get("body", {}))
            assert "parents" not in body
        finally:
            os.unlink(path)

    def test_drive_api_called_with_correct_mimetypes(self):
        svc = _drive_create_ok()
        ctx = _mock_ctx(drive_service=svc)
        path = _write_temp_html("<p>test</p>")

        try:
            create_document("Title", path, ctx=ctx)

            create_call = svc.files().create.call_args
            body = create_call.kwargs.get("body", create_call[1].get("body", {}))
            assert body["mimeType"] == "application/vnd.google-apps.document"
        finally:
            os.unlink(path)

    def test_html_content_passed_as_media(self):
        """Verify MediaInMemoryUpload is used with text/html mimetype."""
        svc = _drive_create_ok()
        ctx = _mock_ctx(drive_service=svc)
        path = _write_temp_html("<p>hello</p>")

        try:
            with patch(
                "mcp_google_workspace.tools.docs.manage.MediaInMemoryUpload"
            ) as mock_media:
                mock_media.return_value = MagicMock()
                create_document("Title", path, ctx=ctx)

                mock_media.assert_called_once()
                call_args = mock_media.call_args
                html_bytes = call_args[0][0]
                assert html_bytes == b"<p>hello</p>"
                assert call_args.kwargs.get("mimetype") == "text/html"
        finally:
            os.unlink(path)

    def test_utf8_html_encoded_properly(self):
        """Non-ASCII HTML should be encoded as UTF-8."""
        svc = _drive_create_ok()
        ctx = _mock_ctx(drive_service=svc)
        html = "<p>日本語テスト</p>"
        path = _write_temp_html(html)

        try:
            with patch(
                "mcp_google_workspace.tools.docs.manage.MediaInMemoryUpload"
            ) as mock_media:
                mock_media.return_value = MagicMock()
                create_document("Title", path, ctx=ctx)

                html_bytes = mock_media.call_args[0][0]
                assert html_bytes == html.encode("utf-8")
        finally:
            os.unlink(path)

    def test_root_folder_when_no_parents_in_response(self):
        svc = _drive_create_ok(parents=None)
        ctx = _mock_ctx(drive_service=svc)
        path = _write_temp_html("<p>test</p>")

        try:
            result = create_document("Title", path, ctx=ctx)
            assert result["folder"] == "root"
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestCreateDocumentErrors:
    def test_api_error_propagated(self):
        svc = MagicMock()
        svc.files().create().execute.side_effect = Exception("Quota exceeded")
        ctx = _mock_ctx(drive_service=svc)
        path = _write_temp_html("<p>test</p>")

        try:
            result = create_document("Title", path, ctx=ctx)
            assert "error" in result
            assert "unexpected error" in result["error"]
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestHtmlConstants:
    def test_max_html_bytes_reasonable(self):
        assert MAX_HTML_BYTES >= 100_000
        assert MAX_HTML_BYTES <= 10_000_000
