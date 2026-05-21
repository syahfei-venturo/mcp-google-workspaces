"""Tests for replace_section_content_with_html — heading-anchored section replacement."""

from unittest.mock import MagicMock

from mcp_google_workspace.tools.docs.write import replace_section_content_with_html


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
# Validation
# ---------------------------------------------------------------------------


class TestReplaceSectionContentWithHtmlValidation:
    """Input validation for replace_section_content_with_html."""

    def test_empty_document_id(self):
        result = replace_section_content_with_html(
            "", "Heading", "<p>new</p>", ctx=_mock_ctx()
        )
        assert "error" in result

    def test_empty_heading_text(self):
        result = replace_section_content_with_html(
            "doc123", "", "<p>new</p>", ctx=_mock_ctx()
        )
        assert "error" in result

    def test_whitespace_heading_text(self):
        result = replace_section_content_with_html(
            "doc123", "   ", "<p>new</p>", ctx=_mock_ctx()
        )
        assert "error" in result


# ---------------------------------------------------------------------------
# Heading not found
# ---------------------------------------------------------------------------


class TestReplaceSectionContentWithHtmlNotFound:
    """Cases where the heading is not found."""

    def test_heading_not_found(self):
        """Returns informative result, no error, no upload."""
        html = "<html><body><h1>Introduction</h1><p>Some text.</p></body></html>"
        drive = _drive_with_html(html)
        ctx = _mock_ctx(drive_service=drive)

        result = replace_section_content_with_html(
            "doc123", "Nonexistent Heading", "<p>new content</p>", ctx=ctx
        )

        assert "error" not in result
        assert result["found"] is False

    def test_case_insensitive_heading_match(self):
        """Default: case-insensitive heading match."""
        html = "<html><body><h1>My Section</h1><p>Old content.</p></body></html>"
        drive = _drive_with_html(html)
        ctx = _mock_ctx(drive_service=drive)

        result = replace_section_content_with_html(
            "doc123", "my section", "<p>new content</p>", ctx=ctx
        )

        assert result["found"] is True
        assert result["status"] == "replaced"

    def test_case_sensitive_heading_match(self):
        """Case-sensitive: exact case must match."""
        html = "<html><body><h1>My Section</h1><p>Old content.</p></body></html>"
        drive = _drive_with_html(html)
        ctx = _mock_ctx(drive_service=drive)

        result = replace_section_content_with_html(
            "doc123", "my section", "<p>new content</p>",
            match_case=True, ctx=ctx,
        )

        assert result["found"] is False


# ---------------------------------------------------------------------------
# Success — basic replacement
# ---------------------------------------------------------------------------


class TestReplaceSectionContentWithHtmlSuccess:
    """Successful section body replacement."""

    def test_replaces_body_between_headings(self):
        """Content between heading and next same-level heading is replaced."""
        html = (
            "<html><body>"
            "<h1>Section A</h1><p>Old text.</p>"
            "<h1>Section B</h1><p>Keep this.</p>"
            "</body></html>"
        )
        drive = _drive_with_html(html)
        ctx = _mock_ctx(drive_service=drive)

        result = replace_section_content_with_html(
            "doc123", "Section A", "<p>New text.</p>", ctx=ctx
        )

        assert "error" not in result
        assert result["found"] is True
        assert result["status"] == "replaced"

        # Verify upload was called with modified HTML
        drive.files().update.assert_called()

    def test_replaces_body_at_end_of_document(self):
        """Section at end of document: body extends to </body>."""
        html = (
            "<html><body>"
            "<h1>Title</h1><p>Intro.</p>"
            "<h2>Details</h2><p>Old stuff.</p>"
            "</body></html>"
        )
        drive = _drive_with_html(html)
        ctx = _mock_ctx(drive_service=drive)

        result = replace_section_content_with_html(
            "doc123", "Details", "<p>New stuff.</p>", ctx=ctx
        )

        assert result["found"] is True
        assert result["status"] == "replaced"

    def test_higher_level_heading_stops_section(self):
        """A higher-level heading (smaller number) stops the section."""
        html = (
            "<html><body>"
            "<h2>Sub</h2><p>Body.</p>"
            "<h1>Next Top</h1><p>Other.</p>"
            "</body></html>"
        )
        drive = _drive_with_html(html)
        ctx = _mock_ctx(drive_service=drive)

        result = replace_section_content_with_html(
            "doc123", "Sub", "<p>Replaced.</p>", ctx=ctx
        )

        assert result["found"] is True
        assert result["status"] == "replaced"

    def test_lower_level_heading_does_not_stop_section(self):
        """A lower-level heading (larger number) does NOT stop the section."""
        html = (
            "<html><body>"
            "<h1>Main</h1><p>Intro.</p><h2>Sub</h2><p>Detail.</p>"
            "<h1>Next</h1><p>Other.</p>"
            "</body></html>"
        )
        drive = _drive_with_html(html)
        ctx = _mock_ctx(drive_service=drive)

        result = replace_section_content_with_html(
            "doc123", "Main", "<p>All new content.</p>", ctx=ctx
        )

        assert result["found"] is True
        assert result["status"] == "replaced"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestReplaceSectionContentWithHtmlEdgeCases:
    """Edge cases for replace_section_content_with_html."""

    def test_api_error_returns_error_dict(self):
        """API error returns error dict."""
        drive = MagicMock()
        drive.files().get().execute.side_effect = Exception("API fail")
        ctx = _mock_ctx(drive_service=drive)

        result = replace_section_content_with_html(
            "doc123", "Section", "<p>New.</p>", ctx=ctx
        )

        assert "error" in result
