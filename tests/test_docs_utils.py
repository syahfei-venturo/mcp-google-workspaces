"""Tests for Google Docs shared utilities (_utils.py)."""

import json
from unittest.mock import MagicMock, patch

from googleapiclient.errors import HttpError

from mcp_google_workspace.tools.docs._utils import (
    pt,
    safe_batch_update,
    safe_get_document,
    validate_document_id,
    validate_uri,
)


class TestValidateDocumentId:
    """Tests for validate_document_id."""

    def test_valid_id(self):
        assert validate_document_id("abc123") is None

    def test_empty_string(self):
        result = validate_document_id("")
        assert result is not None
        assert "error" in result

    def test_whitespace_only(self):
        result = validate_document_id("   ")
        assert result is not None
        assert "error" in result

    def test_none_value(self):
        result = validate_document_id(None)
        assert result is not None
        assert "error" in result


class TestPt:
    """Tests for pt helper."""

    def test_builds_dimension(self):
        result = pt(12.5)
        assert result == {"magnitude": 12.5, "unit": "PT"}

    def test_zero(self):
        result = pt(0)
        assert result == {"magnitude": 0, "unit": "PT"}


class TestValidateUri:
    """Tests for validate_uri."""

    def test_valid_https(self):
        assert validate_uri("https://example.com/image.png") is None

    def test_empty_string(self):
        result = validate_uri("")
        assert result is not None
        assert "error" in result

    def test_whitespace_only(self):
        result = validate_uri("   ")
        assert result is not None

    def test_http_rejected(self):
        result = validate_uri("http://example.com/image.png")
        assert result is not None
        assert "HTTPS" in result["error"]

    def test_ftp_rejected(self):
        result = validate_uri("ftp://example.com/file")
        assert result is not None
        assert "HTTPS" in result["error"]

    def test_no_scheme_rejected(self):
        result = validate_uri("example.com/image.png")
        assert result is not None

    def test_case_insensitive_https(self):
        assert validate_uri("HTTPS://example.com/img.png") is None


class TestSafeBatchUpdate:
    """Tests for safe_batch_update."""

    def test_success(self):
        svc = MagicMock()
        expected = {"replies": [{}]}
        svc.documents().batchUpdate().execute.return_value = expected

        result = safe_batch_update(svc, "doc1", [{"insertText": {}}])
        assert result == expected

    def test_http_error_with_json(self):
        svc = MagicMock()
        error_body = json.dumps(
            {"error": {"message": "Document not found", "code": 404}}
        ).encode()
        http_error = HttpError(
            resp=MagicMock(status=404),
            content=error_body,
        )
        svc.documents().batchUpdate().execute.side_effect = http_error

        result = safe_batch_update(svc, "doc1", [{"insertText": {}}])
        assert "error" in result
        assert "Document not found" in result["error"]

    def test_http_error_non_retryable(self):
        """Non-retryable errors (e.g. 404) fail immediately without retry."""
        svc = MagicMock()
        http_error = HttpError(
            resp=MagicMock(status=404),
            content=b"Not Found",
        )
        svc.documents().batchUpdate().execute.side_effect = http_error

        result = safe_batch_update(svc, "doc1", [{"insertText": {}}])
        assert "error" in result
        assert "Google API error" in result["error"]
        # Called only once — no retry
        assert svc.documents().batchUpdate().execute.call_count == 1

    def test_generic_exception(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.side_effect = RuntimeError("boom")

        result = safe_batch_update(svc, "doc1", [{"insertText": {}}])
        assert "error" in result
        assert "Failed to update document" in result["error"]
        assert "boom" in result["error"]

    @patch("mcp_google_workspace.tools.docs._utils.time.sleep")
    def test_retry_on_429(self, mock_sleep):
        """HTTP 429 triggers retry with backoff, then succeeds."""
        svc = MagicMock()
        rate_limit_error = HttpError(
            resp=MagicMock(status=429),
            content=json.dumps(
                {"error": {"message": "Quota exceeded", "code": 429}}
            ).encode(),
        )
        expected = {"replies": [{}]}
        svc.documents().batchUpdate().execute.side_effect = [
            rate_limit_error,
            rate_limit_error,
            expected,
        ]

        result = safe_batch_update(svc, "doc1", [{"insertText": {}}])
        assert result == expected
        assert svc.documents().batchUpdate().execute.call_count == 3
        assert mock_sleep.call_count == 2
        # Verify exponential backoff: 2.0, 4.0
        assert mock_sleep.call_args_list[0][0][0] == 2.0
        assert mock_sleep.call_args_list[1][0][0] == 4.0

    @patch("mcp_google_workspace.tools.docs._utils.time.sleep")
    def test_retry_on_500(self, mock_sleep):
        """HTTP 500 triggers retry."""
        svc = MagicMock()
        server_error = HttpError(
            resp=MagicMock(status=500),
            content=b"Internal Server Error",
        )
        expected = {"replies": [{}]}
        svc.documents().batchUpdate().execute.side_effect = [
            server_error,
            expected,
        ]

        result = safe_batch_update(svc, "doc1", [{"insertText": {}}])
        assert result == expected
        assert mock_sleep.call_count == 1

    @patch("mcp_google_workspace.tools.docs._utils.time.sleep")
    def test_retry_exhausted(self, mock_sleep):
        """All retries exhausted returns error."""
        svc = MagicMock()
        rate_limit_error = HttpError(
            resp=MagicMock(status=429),
            content=json.dumps(
                {"error": {"message": "Quota exceeded", "code": 429}}
            ).encode(),
        )
        # All attempts fail
        svc.documents().batchUpdate().execute.side_effect = rate_limit_error

        result = safe_batch_update(svc, "doc1", [{"insertText": {}}])
        assert "error" in result
        assert "Quota exceeded" in result["error"]
        # 1 initial + 5 retries = 6 total
        assert svc.documents().batchUpdate().execute.call_count == 6


class TestSafeGetDocument:
    """Tests for safe_get_document."""

    def test_success(self):
        svc = MagicMock()
        expected = {"body": {"content": []}, "documentId": "doc1"}
        svc.documents().get().execute.return_value = expected

        result = safe_get_document(svc, "doc1")
        assert result == expected

    def test_non_retryable_error(self):
        svc = MagicMock()
        http_error = HttpError(
            resp=MagicMock(status=404),
            content=b"Not Found",
        )
        svc.documents().get().execute.side_effect = http_error

        result = safe_get_document(svc, "doc1")
        assert "error" in result
        assert svc.documents().get().execute.call_count == 1

    @patch("mcp_google_workspace.tools.docs._utils.time.sleep")
    def test_retry_on_429(self, mock_sleep):
        svc = MagicMock()
        rate_limit_error = HttpError(
            resp=MagicMock(status=429),
            content=json.dumps(
                {"error": {"message": "Quota exceeded"}}
            ).encode(),
        )
        expected = {"body": {"content": []}, "documentId": "doc1"}
        svc.documents().get().execute.side_effect = [
            rate_limit_error,
            expected,
        ]

        result = safe_get_document(svc, "doc1")
        assert result == expected
        assert mock_sleep.call_count == 1

    @patch("mcp_google_workspace.tools.docs._utils.time.sleep")
    def test_retry_exhausted(self, mock_sleep):
        svc = MagicMock()
        rate_limit_error = HttpError(
            resp=MagicMock(status=429),
            content=json.dumps(
                {"error": {"message": "Quota exceeded"}}
            ).encode(),
        )
        svc.documents().get().execute.side_effect = rate_limit_error

        result = safe_get_document(svc, "doc1")
        assert "error" in result
        assert svc.documents().get().execute.call_count == 6

    def test_generic_exception(self):
        svc = MagicMock()
        svc.documents().get().execute.side_effect = RuntimeError("network")

        result = safe_get_document(svc, "doc1")
        assert "error" in result
        assert "network" in result["error"]
