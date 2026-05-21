"""Tests for replace_first_text_with_html and replace_text_in_range_with_html."""

from unittest.mock import MagicMock

from mcp_google_workspace.tools.docs.write import (
    replace_first_text_with_html,
    replace_text_in_range_with_html,
)


def _mock_ctx(drive_service=None):
    """Build a mock Context with lifespan_context services."""
    ctx = MagicMock()
    lifespan = MagicMock()
    lifespan.drive_service = drive_service or MagicMock()
    ctx.request_context.lifespan_context = lifespan
    return ctx


def _drive_with_html(html_content: str):
    """Build a mock drive service that exports the given HTML."""
    drive = MagicMock()
    drive.files().get().execute.return_value = {"id": "doc123", "name": "Test Doc"}
    drive.files().export().execute.return_value = html_content.encode("utf-8")
    drive.files().update().execute.return_value = {"id": "doc123"}
    return drive


# ---------------------------------------------------------------------------
# replace_first_text_with_html — validation
# ---------------------------------------------------------------------------


class TestReplaceFirstTextWithHtmlValidation:
    """Input validation for replace_first_text_with_html."""

    def test_empty_document_id(self):
        result = replace_first_text_with_html("", "old", "<b>new</b>", ctx=_mock_ctx())
        assert "error" in result

    def test_empty_find_text(self):
        result = replace_first_text_with_html("doc123", "", "<b>new</b>", ctx=_mock_ctx())
        assert "error" in result

    def test_whitespace_find_text(self):
        result = replace_first_text_with_html("doc123", "   ", "<b>new</b>", ctx=_mock_ctx())
        assert "error" in result


# ---------------------------------------------------------------------------
# replace_first_text_with_html — success cases
# ---------------------------------------------------------------------------


class TestReplaceFirstTextWithHtmlSuccess:
    """Successful replace_first_text_with_html operations."""

    def test_replaces_only_first_occurrence(self):
        """When text appears multiple times, only the first is replaced."""
        html = "<html><body><p>foo bar foo baz foo</p></body></html>"
        drive = _drive_with_html(html)
        ctx = _mock_ctx(drive_service=drive)

        result = replace_first_text_with_html(
            "doc123", "foo", "<b>replaced</b>", ctx=ctx
        )

        assert "error" not in result
        assert result["documentId"] == "doc123"
        assert result["occurrencesFound"] == 3
        assert result["status"] == "replaced_first"

        # Verify upload was called
        drive.files().update.assert_called()

    def test_case_insensitive_match(self):
        """Case-insensitive matching finds the first occurrence."""
        html = "<html><body><p>Hello HELLO hello</p></body></html>"
        drive = _drive_with_html(html)
        ctx = _mock_ctx(drive_service=drive)

        result = replace_first_text_with_html(
            "doc123", "hello", "<em>hi</em>", match_case=False, ctx=ctx
        )

        assert "error" not in result
        assert result["occurrencesFound"] == 3

    def test_case_sensitive_match(self):
        """Case-sensitive matching skips non-matching case."""
        html = "<html><body><p>Hello HELLO hello</p></body></html>"
        drive = _drive_with_html(html)
        ctx = _mock_ctx(drive_service=drive)

        result = replace_first_text_with_html(
            "doc123", "HELLO", "<em>hi</em>", match_case=True, ctx=ctx
        )

        assert "error" not in result
        assert result["occurrencesFound"] == 1


# ---------------------------------------------------------------------------
# replace_first_text_with_html — no match
# ---------------------------------------------------------------------------


class TestReplaceFirstTextWithHtmlEdgeCases:
    """Edge cases for replace_first_text_with_html."""

    def test_no_match_returns_zero(self):
        """When text is not found, return informative result without error."""
        html = "<html><body><p>Hello World</p></body></html>"
        drive = _drive_with_html(html)
        ctx = _mock_ctx(drive_service=drive)

        result = replace_first_text_with_html(
            "doc123", "xyz", "<b>new</b>", ctx=ctx
        )

        assert "error" not in result
        assert result["occurrencesFound"] == 0


# ---------------------------------------------------------------------------
# replace_text_in_range_with_html — validation
# ---------------------------------------------------------------------------


class TestReplaceTextInRangeWithHtmlValidation:
    """Input validation for replace_text_in_range_with_html."""

    def test_empty_document_id(self):
        result = replace_text_in_range_with_html(
            "", "old", "<b>new</b>", "start", "end", ctx=_mock_ctx()
        )
        assert "error" in result

    def test_empty_find_text(self):
        result = replace_text_in_range_with_html(
            "doc123", "", "<b>new</b>", "start", "end", ctx=_mock_ctx()
        )
        assert "error" in result

    def test_empty_range_start(self):
        result = replace_text_in_range_with_html(
            "doc123", "old", "<b>new</b>", "", "end", ctx=_mock_ctx()
        )
        assert "error" in result

    def test_empty_range_end(self):
        result = replace_text_in_range_with_html(
            "doc123", "old", "<b>new</b>", "start", "", ctx=_mock_ctx()
        )
        assert "error" in result


# ---------------------------------------------------------------------------
# replace_text_in_range_with_html — success cases
# ---------------------------------------------------------------------------


class TestReplaceTextInRangeWithHtmlSuccess:
    """Successful replace_text_in_range_with_html operations."""

    def test_replaces_within_range(self):
        """Replaces all occurrences within the bounded range."""
        html = (
            "<html><body>"
            "<h1>Section A</h1><p>foo bar foo</p>"
            "<h1>Section B</h1><p>foo baz</p>"
            "</body></html>"
        )
        drive = _drive_with_html(html)
        ctx = _mock_ctx(drive_service=drive)

        result = replace_text_in_range_with_html(
            "doc123", "foo", "<b>X</b>",
            range_start_text="Section A",
            range_end_text="Section B",
            ctx=ctx,
        )

        assert "error" not in result
        assert result["occurrencesReplaced"] == 2
        assert result["status"] == "replaced"

    def test_no_match_in_range(self):
        """No match within range returns zero."""
        html = (
            "<html><body>"
            "<h1>Start</h1><p>abc def</p>"
            "<h1>End</h1>"
            "</body></html>"
        )
        drive = _drive_with_html(html)
        ctx = _mock_ctx(drive_service=drive)

        result = replace_text_in_range_with_html(
            "doc123", "xyz", "<b>new</b>",
            range_start_text="Start",
            range_end_text="End",
            ctx=ctx,
        )

        assert result["occurrencesReplaced"] == 0

    def test_range_start_not_found(self):
        """When range_start_text not found, return error."""
        html = "<html><body><p>Hello World</p></body></html>"
        drive = _drive_with_html(html)
        ctx = _mock_ctx(drive_service=drive)

        result = replace_text_in_range_with_html(
            "doc123", "Hello", "<b>Hi</b>",
            range_start_text="Nonexistent",
            range_end_text="World",
            ctx=ctx,
        )

        assert "error" in result
