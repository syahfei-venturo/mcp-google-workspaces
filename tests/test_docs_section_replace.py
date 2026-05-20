"""Tests for replace_section_content — heading-anchored section replacement."""

from unittest.mock import MagicMock

from mcp_google_workspace.tools.docs.write import replace_section_content


def _mock_ctx(docs_service=None):
    """Build a mock Context with lifespan_context services."""
    ctx = MagicMock()
    lifespan = MagicMock()
    lifespan.docs_service = docs_service or MagicMock()
    ctx.request_context.lifespan_context = lifespan
    return ctx


def _heading(text, start_index, level=1):
    """Build a heading paragraph element."""
    return {
        "paragraph": {
            "elements": [{"textRun": {"content": text}}],
            "paragraphStyle": {"namedStyleType": f"HEADING_{level}"},
        },
        "startIndex": start_index,
        "endIndex": start_index + len(text),
    }


def _para(text, start_index):
    """Build a normal paragraph element."""
    return {
        "paragraph": {
            "elements": [{"textRun": {"content": text}}],
            "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
        },
        "startIndex": start_index,
        "endIndex": start_index + len(text),
    }


def _doc(content, doc_id="doc123", title="Test Doc"):
    """Build a minimal Google Docs API document response."""
    return {
        "documentId": doc_id,
        "title": title,
        "body": {"content": content},
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestReplaceSectionContentValidation:
    """Input validation for replace_section_content."""

    def test_empty_document_id(self):
        result = replace_section_content("", "Heading", "new", ctx=_mock_ctx())
        assert "error" in result

    def test_empty_heading_text(self):
        result = replace_section_content("doc123", "", "new", ctx=_mock_ctx())
        assert "error" in result

    def test_whitespace_heading_text(self):
        result = replace_section_content("doc123", "   ", "new", ctx=_mock_ctx())
        assert "error" in result


# ---------------------------------------------------------------------------
# Heading not found
# ---------------------------------------------------------------------------


class TestReplaceSectionContentNotFound:
    """Cases where the heading is not found."""

    def test_heading_not_found(self):
        """Returns informative result, no error, no batchUpdate."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = _doc(
            [
                _heading("Introduction\n", 1, level=1),
                _para("Some body text.\n", 14),
            ]
        )
        ctx = _mock_ctx(docs_service=svc)

        result = replace_section_content(
            "doc123", "Nonexistent Heading", "new content", ctx=ctx
        )

        assert "error" not in result
        assert result["found"] is False
        svc.documents().batchUpdate.assert_not_called()

    def test_case_insensitive_heading_match(self):
        """Default: case-insensitive heading match."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = _doc(
            [
                _heading("My Section\n", 1, level=1),
                _para("Old content.\n", 12),
            ]
        )
        svc.documents().batchUpdate().execute.return_value = {"replies": [{}, {}]}
        ctx = _mock_ctx(docs_service=svc)

        result = replace_section_content(
            "doc123", "my section", "new content", ctx=ctx
        )

        assert result["found"] is True

    def test_case_sensitive_heading_match(self):
        """Case-sensitive: exact case must match."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = _doc(
            [
                _heading("My Section\n", 1, level=1),
                _para("Old content.\n", 12),
            ]
        )
        ctx = _mock_ctx(docs_service=svc)

        result = replace_section_content(
            "doc123", "my section", "new content",
            match_case=True, ctx=ctx,
        )

        assert result["found"] is False


# ---------------------------------------------------------------------------
# Success — basic replacement
# ---------------------------------------------------------------------------


class TestReplaceSectionContentSuccess:
    """Successful section body replacement."""

    def test_replaces_body_between_headings(self):
        """Content between heading and next same-level heading is replaced."""
        # Document structure:
        #   H1 "Section A\n"    indices 1-11
        #   P  "Old text.\n"    indices 11-21
        #   H1 "Section B\n"    indices 21-31
        #   P  "Keep this.\n"   indices 31-42
        svc = MagicMock()
        svc.documents().get().execute.return_value = _doc(
            [
                _heading("Section A\n", 1, level=1),
                _para("Old text.\n", 11, ),
                _heading("Section B\n", 21, level=1),
                _para("Keep this.\n", 31),
            ]
        )
        svc.documents().batchUpdate().execute.return_value = {"replies": [{}, {}]}
        ctx = _mock_ctx(docs_service=svc)

        result = replace_section_content(
            "doc123", "Section A", "New text.\n", ctx=ctx
        )

        assert "error" not in result
        assert result["found"] is True
        assert result["documentId"] == "doc123"
        assert result["headingText"] == "Section A"
        # Section body: indices 11-21 (after heading, before next H1)
        assert result["sectionRange"]["startIndex"] == 11
        assert result["sectionRange"]["endIndex"] == 21

        # Verify batchUpdate: delete old content + insert new
        batch_calls = [
            c for c in svc.documents().batchUpdate.call_args_list
            if c[1]  # filter setup calls
        ]
        assert len(batch_calls) == 1
        requests = batch_calls[0][1]["body"]["requests"]
        assert "deleteContentRange" in requests[0]
        assert requests[0]["deleteContentRange"]["range"]["startIndex"] == 11
        assert requests[0]["deleteContentRange"]["range"]["endIndex"] == 21
        assert "insertText" in requests[1]
        assert requests[1]["insertText"]["text"] == "New text.\n"
        assert requests[1]["insertText"]["location"]["index"] == 11

    def test_replaces_body_at_end_of_document(self):
        """Section at end of document: body extends to last element's endIndex."""
        # Document structure:
        #   H1 "Title\n"      indices 1-7
        #   P  "Intro.\n"     indices 7-14
        #   H2 "Details\n"    indices 14-22
        #   P  "Old stuff.\n" indices 22-33
        svc = MagicMock()
        svc.documents().get().execute.return_value = _doc(
            [
                _heading("Title\n", 1, level=1),
                _para("Intro.\n", 7),
                _heading("Details\n", 14, level=2),
                _para("Old stuff.\n", 22),
            ]
        )
        svc.documents().batchUpdate().execute.return_value = {"replies": [{}, {}]}
        ctx = _mock_ctx(docs_service=svc)

        result = replace_section_content(
            "doc123", "Details", "New stuff.\n", ctx=ctx
        )

        assert result["found"] is True
        # Section body starts after "Details\n" heading, goes to end of doc
        assert result["sectionRange"]["startIndex"] == 22
        assert result["sectionRange"]["endIndex"] == 33

    def test_higher_level_heading_stops_section(self):
        """A higher-level heading (smaller number) stops the section."""
        # H2 "Sub\n"        indices 1-5
        # P  "Body.\n"      indices 5-11
        # H1 "Next Top\n"   indices 11-20
        svc = MagicMock()
        svc.documents().get().execute.return_value = _doc(
            [
                _heading("Sub\n", 1, level=2),
                _para("Body.\n", 5),
                _heading("Next Top\n", 11, level=1),
            ]
        )
        svc.documents().batchUpdate().execute.return_value = {"replies": [{}, {}]}
        ctx = _mock_ctx(docs_service=svc)

        result = replace_section_content(
            "doc123", "Sub", "Replaced.\n", ctx=ctx
        )

        assert result["found"] is True
        # H1 stops the H2 section
        assert result["sectionRange"]["startIndex"] == 5
        assert result["sectionRange"]["endIndex"] == 11

    def test_lower_level_heading_does_not_stop_section(self):
        """A lower-level heading (larger number) does NOT stop the section."""
        # H1 "Main\n"     indices 1-6
        # P  "Intro.\n"   indices 6-13
        # H2 "Sub\n"      indices 13-17
        # P  "Detail.\n"  indices 17-25
        # H1 "Next\n"     indices 25-30
        svc = MagicMock()
        svc.documents().get().execute.return_value = _doc(
            [
                _heading("Main\n", 1, level=1),
                _para("Intro.\n", 6),
                _heading("Sub\n", 13, level=2),
                _para("Detail.\n", 17),
                _heading("Next\n", 25, level=1),
            ]
        )
        svc.documents().batchUpdate().execute.return_value = {"replies": [{}, {}]}
        ctx = _mock_ctx(docs_service=svc)

        result = replace_section_content(
            "doc123", "Main", "All new content.\n", ctx=ctx
        )

        assert result["found"] is True
        # H2 "Sub" is inside H1 "Main" section — not a boundary
        # Section extends from after "Main\n" (6) to "Next\n" (25)
        assert result["sectionRange"]["startIndex"] == 6
        assert result["sectionRange"]["endIndex"] == 25

    def test_empty_replacement_deletes_section_body(self):
        """Empty replacement string effectively deletes section content."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = _doc(
            [
                _heading("Remove Me\n", 1, level=1),
                _para("Gone.\n", 11),
                _heading("Keep\n", 17, level=1),
            ]
        )
        svc.documents().batchUpdate().execute.return_value = {"replies": [{}]}
        ctx = _mock_ctx(docs_service=svc)

        result = replace_section_content(
            "doc123", "Remove Me", "", ctx=ctx
        )

        assert result["found"] is True
        # Only delete request, no insert
        batch_calls = [
            c for c in svc.documents().batchUpdate.call_args_list
            if c[1]
        ]
        requests = batch_calls[0][1]["body"]["requests"]
        assert len(requests) == 1
        assert "deleteContentRange" in requests[0]

    def test_single_atomic_batch_update(self):
        """All operations in a single batchUpdate call."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = _doc(
            [
                _heading("Section\n", 1, level=1),
                _para("Old.\n", 9),
            ]
        )
        svc.documents().batchUpdate().execute.return_value = {"replies": [{}, {}]}
        ctx = _mock_ctx(docs_service=svc)

        replace_section_content("doc123", "Section", "New.\n", ctx=ctx)

        batch_calls = [
            c for c in svc.documents().batchUpdate.call_args_list
            if c[1]
        ]
        assert len(batch_calls) == 1


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestReplaceSectionContentEdgeCases:
    """Edge cases for replace_section_content."""

    def test_empty_section_with_empty_replacement_noop(self):
        """Empty section body + empty replacement = no batchUpdate call."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = _doc(
            [
                _heading("A\n", 1, level=1),
                _heading("B\n", 3, level=1),
            ]
        )
        ctx = _mock_ctx(docs_service=svc)

        result = replace_section_content("doc123", "A", "", ctx=ctx)

        assert result["found"] is True
        assert result["sectionRange"]["startIndex"] == 3
        assert result["sectionRange"]["endIndex"] == 3
        svc.documents().batchUpdate.assert_not_called()

    def test_heading_with_no_body(self):
        """Heading immediately followed by another heading — empty section body."""
        # H1 "A\n" indices 1-3, H1 "B\n" indices 3-5
        svc = MagicMock()
        svc.documents().get().execute.return_value = _doc(
            [
                _heading("A\n", 1, level=1),
                _heading("B\n", 3, level=1),
            ]
        )
        ctx = _mock_ctx(docs_service=svc)

        result = replace_section_content(
            "doc123", "A", "Inserted.\n", ctx=ctx
        )

        assert result["found"] is True
        # Empty range: start == end
        assert result["sectionRange"]["startIndex"] == 3
        assert result["sectionRange"]["endIndex"] == 3

    def test_multiple_headings_same_text_replaces_first(self):
        """When multiple headings have the same text, replace under the first."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = _doc(
            [
                _heading("Dup\n", 1, level=1),
                _para("First body.\n", 5),
                _heading("Dup\n", 17, level=1),
                _para("Second body.\n", 21),
            ]
        )
        svc.documents().batchUpdate().execute.return_value = {"replies": [{}, {}]}
        ctx = _mock_ctx(docs_service=svc)

        result = replace_section_content(
            "doc123", "Dup", "Replaced.\n", ctx=ctx
        )

        assert result["found"] is True
        # First "Dup" section body: 5-17
        assert result["sectionRange"]["startIndex"] == 5
        assert result["sectionRange"]["endIndex"] == 17

    def test_heading_text_stripped_for_match(self):
        """Heading text should be stripped of trailing newline for matching."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = _doc(
            [
                _heading("My Heading\n", 1, level=1),
                _para("Body.\n", 12),
            ]
        )
        svc.documents().batchUpdate().execute.return_value = {"replies": [{}, {}]}
        ctx = _mock_ctx(docs_service=svc)

        # User passes "My Heading" without newline
        result = replace_section_content(
            "doc123", "My Heading", "New.\n", ctx=ctx
        )

        assert result["found"] is True

    def test_api_error_returns_error_dict(self):
        """API error via safe_batch_update returns error dict."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = _doc(
            [
                _heading("Section\n", 1, level=1),
                _para("Body.\n", 9),
            ]
        )
        svc.documents().batchUpdate().execute.side_effect = Exception("API fail")
        ctx = _mock_ctx(docs_service=svc)

        result = replace_section_content(
            "doc123", "Section", "New.\n", ctx=ctx
        )

        assert "error" in result

    def test_document_not_found_raises(self):
        """API error on get propagates as exception."""
        svc = MagicMock()
        svc.documents().get().execute.side_effect = Exception("Not found")
        ctx = _mock_ctx(docs_service=svc)

        try:
            replace_section_content("doc123", "Section", "New.\n", ctx=ctx)
            assert False, "Should have raised"
        except Exception as e:
            assert "Not found" in str(e)

    def test_section_with_table_included(self):
        """Tables within a section are part of the section body."""
        svc = MagicMock()
        table_elem = {
            "table": {
                "rows": 1,
                "columns": 1,
                "tableRows": [
                    {
                        "tableCells": [
                            {
                                "content": [
                                    {
                                        "paragraph": {
                                            "elements": [
                                                {"textRun": {"content": "Cell"}}
                                            ]
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ],
            },
            "startIndex": 9,
            "endIndex": 25,
        }
        svc.documents().get().execute.return_value = _doc(
            [
                _heading("Section\n", 1, level=1),
                table_elem,
                _heading("Next\n", 25, level=1),
            ]
        )
        svc.documents().batchUpdate().execute.return_value = {"replies": [{}, {}]}
        ctx = _mock_ctx(docs_service=svc)

        result = replace_section_content(
            "doc123", "Section", "No table.\n", ctx=ctx
        )

        assert result["found"] is True
        # Section body includes the table: 9-25
        assert result["sectionRange"]["startIndex"] == 9
        assert result["sectionRange"]["endIndex"] == 25

    def test_only_heading_in_document(self):
        """Document with just a heading and nothing after — empty section."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = _doc(
            [_heading("Alone\n", 1, level=1)]
        )
        ctx = _mock_ctx(docs_service=svc)

        result = replace_section_content(
            "doc123", "Alone", "New content.\n", ctx=ctx
        )

        assert result["found"] is True
        # endIndex of heading == start and end of empty section body
        assert result["sectionRange"]["startIndex"] == 7
        assert result["sectionRange"]["endIndex"] == 7
