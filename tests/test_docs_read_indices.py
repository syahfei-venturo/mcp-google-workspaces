"""Tests for get_text_with_indices — document text annotated with character indices."""

from unittest.mock import MagicMock

from mcp_google_workspace.tools.docs.read import get_text_with_indices


def _mock_ctx(docs_service=None):
    """Build a mock Context with lifespan_context services."""
    ctx = MagicMock()
    lifespan = MagicMock()
    lifespan.docs_service = docs_service or MagicMock()
    ctx.request_context.lifespan_context = lifespan
    return ctx


def _doc(content, doc_id="doc123", title="Test Doc"):
    """Build a minimal Google Docs API document response."""
    return {
        "documentId": doc_id,
        "title": title,
        "body": {"content": content},
    }


def _paragraph(text, start_index, heading_id=None, named_style="NORMAL_TEXT"):
    """Build a paragraph structural element with optional heading style."""
    para = {
        "elements": [{"textRun": {"content": text}}],
        "paragraphStyle": {"namedStyleType": named_style},
    }
    if heading_id:
        para["paragraphStyle"]["headingId"] = heading_id
    return {
        "paragraph": para,
        "startIndex": start_index,
        "endIndex": start_index + len(text),
    }


def _table(rows_data, start_index, end_index):
    """Build a table structural element.

    rows_data: list of lists of strings, e.g. [["A","B"],["C","D"]]
    """
    table_rows = []
    for row in rows_data:
        cells = []
        for cell_text in row:
            cells.append(
                {
                    "content": [
                        {
                            "paragraph": {
                                "elements": [{"textRun": {"content": cell_text}}]
                            }
                        }
                    ]
                }
            )
        table_rows.append({"tableCells": cells})
    return {
        "table": {
            "rows": len(rows_data),
            "columns": len(rows_data[0]) if rows_data else 0,
            "tableRows": table_rows,
        },
        "startIndex": start_index,
        "endIndex": end_index,
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestGetTextWithIndicesValidation:
    """Input validation for get_text_with_indices."""

    def test_empty_document_id(self):
        result = get_text_with_indices("", ctx=_mock_ctx())
        assert "error" in result

    def test_whitespace_document_id(self):
        result = get_text_with_indices("   ", ctx=_mock_ctx())
        assert "error" in result


# ---------------------------------------------------------------------------
# Single paragraph
# ---------------------------------------------------------------------------


class TestGetTextWithIndicesSingleParagraph:
    """Single paragraph documents."""

    def test_returns_one_segment(self):
        svc = MagicMock()
        svc.documents().get().execute.return_value = _doc(
            [_paragraph("Hello World\n", 1)]
        )
        ctx = _mock_ctx(docs_service=svc)

        result = get_text_with_indices("doc123", ctx=ctx)

        assert "error" not in result
        assert result["documentId"] == "doc123"
        assert result["title"] == "Test Doc"
        assert len(result["segments"]) == 1

        seg = result["segments"][0]
        assert seg["text"] == "Hello World\n"
        assert seg["startIndex"] == 1
        assert seg["endIndex"] == 1 + len("Hello World\n")
        assert seg["type"] == "paragraph"

    def test_includes_total_length(self):
        svc = MagicMock()
        svc.documents().get().execute.return_value = _doc(
            [_paragraph("Short\n", 1)]
        )
        ctx = _mock_ctx(docs_service=svc)

        result = get_text_with_indices("doc123", ctx=ctx)
        assert result["totalLength"] == len("Short\n")


# ---------------------------------------------------------------------------
# Multiple paragraphs
# ---------------------------------------------------------------------------


class TestGetTextWithIndicesMultiParagraph:
    """Multi-paragraph documents."""

    def test_returns_multiple_segments(self):
        svc = MagicMock()
        svc.documents().get().execute.return_value = _doc(
            [
                _paragraph("First line\n", 1),
                _paragraph("Second line\n", 12),
            ]
        )
        ctx = _mock_ctx(docs_service=svc)

        result = get_text_with_indices("doc123", ctx=ctx)

        assert len(result["segments"]) == 2
        assert result["segments"][0]["startIndex"] == 1
        assert result["segments"][0]["text"] == "First line\n"
        assert result["segments"][1]["startIndex"] == 12
        assert result["segments"][1]["text"] == "Second line\n"

    def test_indices_are_contiguous(self):
        """End of segment N == start of segment N+1."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = _doc(
            [
                _paragraph("AAA\n", 1),
                _paragraph("BBB\n", 5),
                _paragraph("CCC\n", 9),
            ]
        )
        ctx = _mock_ctx(docs_service=svc)

        result = get_text_with_indices("doc123", ctx=ctx)
        segs = result["segments"]
        for i in range(len(segs) - 1):
            assert segs[i]["endIndex"] == segs[i + 1]["startIndex"]


# ---------------------------------------------------------------------------
# Headings
# ---------------------------------------------------------------------------


class TestGetTextWithIndicesHeadings:
    """Heading paragraphs should be annotated with heading level."""

    def test_heading_1_type(self):
        svc = MagicMock()
        svc.documents().get().execute.return_value = _doc(
            [
                _paragraph(
                    "Title\n", 1,
                    heading_id="h1", named_style="HEADING_1",
                ),
                _paragraph("Body text\n", 7),
            ]
        )
        ctx = _mock_ctx(docs_service=svc)

        result = get_text_with_indices("doc123", ctx=ctx)

        assert result["segments"][0]["type"] == "heading_1"
        assert result["segments"][1]["type"] == "paragraph"

    def test_heading_2_type(self):
        svc = MagicMock()
        svc.documents().get().execute.return_value = _doc(
            [
                _paragraph(
                    "Subtitle\n", 1,
                    heading_id="h2", named_style="HEADING_2",
                ),
            ]
        )
        ctx = _mock_ctx(docs_service=svc)

        result = get_text_with_indices("doc123", ctx=ctx)
        assert result["segments"][0]["type"] == "heading_2"

    def test_heading_levels_3_through_6(self):
        """HEADING_3..HEADING_6 map to heading_3..heading_6."""
        for level in range(3, 7):
            svc = MagicMock()
            svc.documents().get().execute.return_value = _doc(
                [
                    _paragraph(
                        f"H{level}\n", 1,
                        named_style=f"HEADING_{level}",
                    ),
                ]
            )
            ctx = _mock_ctx(docs_service=svc)
            result = get_text_with_indices("doc123", ctx=ctx)
            assert result["segments"][0]["type"] == f"heading_{level}"


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


class TestGetTextWithIndicesTables:
    """Table elements should appear as table segments."""

    def test_table_segment(self):
        svc = MagicMock()
        svc.documents().get().execute.return_value = _doc(
            [
                _paragraph("Before table\n", 1),
                _table([["A", "B"], ["C", "D"]], start_index=14, end_index=50),
                _paragraph("After table\n", 50),
            ]
        )
        ctx = _mock_ctx(docs_service=svc)

        result = get_text_with_indices("doc123", ctx=ctx)

        assert len(result["segments"]) == 3
        table_seg = result["segments"][1]
        assert table_seg["type"] == "table"
        assert table_seg["startIndex"] == 14
        assert table_seg["endIndex"] == 50
        # Table text is extracted from cells
        assert "A" in table_seg["text"]
        assert "D" in table_seg["text"]

    def test_table_rows_and_columns(self):
        """Table segment should include row/column counts."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = _doc(
            [_table([["X", "Y", "Z"], ["1", "2", "3"]], 1, 30)]
        )
        ctx = _mock_ctx(docs_service=svc)

        result = get_text_with_indices("doc123", ctx=ctx)
        table_seg = result["segments"][0]
        assert table_seg["rows"] == 2
        assert table_seg["columns"] == 3


# ---------------------------------------------------------------------------
# Empty / edge cases
# ---------------------------------------------------------------------------


class TestGetTextWithIndicesEdgeCases:
    """Edge cases for get_text_with_indices."""

    def test_empty_body_returns_no_segments(self):
        svc = MagicMock()
        svc.documents().get().execute.return_value = _doc([])
        ctx = _mock_ctx(docs_service=svc)

        result = get_text_with_indices("doc123", ctx=ctx)

        assert result["segments"] == []
        assert result["totalLength"] == 0

    def test_section_break_skipped(self):
        """Section breaks should not produce segments."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = _doc(
            [
                _paragraph("Para 1\n", 1),
                {"sectionBreak": {}, "startIndex": 8, "endIndex": 9},
                _paragraph("Para 2\n", 9),
            ]
        )
        ctx = _mock_ctx(docs_service=svc)

        result = get_text_with_indices("doc123", ctx=ctx)

        types = [s["type"] for s in result["segments"]]
        assert "section_break" not in types
        assert len(result["segments"]) == 2

    def test_multi_element_paragraph(self):
        """Paragraph with multiple textRun elements merges text correctly."""
        svc = MagicMock()
        doc = _doc(
            [
                {
                    "paragraph": {
                        "elements": [
                            {"textRun": {"content": "Hello "}},
                            {"textRun": {"content": "World\n"}},
                        ],
                        "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                    },
                    "startIndex": 1,
                    "endIndex": 13,
                }
            ]
        )
        svc.documents().get().execute.return_value = doc
        ctx = _mock_ctx(docs_service=svc)

        result = get_text_with_indices("doc123", ctx=ctx)

        assert len(result["segments"]) == 1
        assert result["segments"][0]["text"] == "Hello World\n"

    def test_empty_paragraph_text(self):
        """Paragraph with empty text produces a segment with empty string."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = _doc(
            [_paragraph("", 1)]
        )
        ctx = _mock_ctx(docs_service=svc)

        result = get_text_with_indices("doc123", ctx=ctx)

        assert len(result["segments"]) == 1
        assert result["segments"][0]["text"] == ""
        assert result["totalLength"] == 0

    def test_table_with_empty_cells(self):
        """Table with empty cells still produces a table segment."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = _doc(
            [_table([["", ""], ["", ""]], start_index=1, end_index=20)]
        )
        ctx = _mock_ctx(docs_service=svc)

        result = get_text_with_indices("doc123", ctx=ctx)

        assert len(result["segments"]) == 1
        assert result["segments"][0]["type"] == "table"
        assert result["segments"][0]["rows"] == 2
        assert result["segments"][0]["columns"] == 2

    def test_api_error_returns_error_dict(self):
        """API exception should return error dict via safe_get_document."""
        svc = MagicMock()
        svc.documents().get().execute.side_effect = Exception("API down")
        ctx = _mock_ctx(docs_service=svc)

        result = get_text_with_indices("doc123", ctx=ctx)
        assert "error" in result
        assert "API down" in result["error"]
