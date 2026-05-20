"""Tests for update_table_cell_content and related index-mapping fixes.

Uses realistic mock document structures with proper cell-level indices
to validate that table cell editing operations target the correct
document positions.
"""

from unittest.mock import MagicMock

from mcp_google_workspace.tools.docs.read import (
    _extract_text_with_positions,
    _text_pos_to_doc_index,
    _text_range_to_doc_range,
    get_tables,
    search_document,
)
from mcp_google_workspace.tools.docs.table import (
    _find_table_element,
    _get_cell_content_range,
    update_table_cell_content,
)
from mcp_google_workspace.tools.docs.write import (
    replace_first_text,
    replace_text_in_range,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _mock_ctx(docs_service=None):
    ctx = MagicMock()
    lifespan = MagicMock()
    lifespan.docs_service = docs_service or MagicMock()
    ctx.request_context.lifespan_context = lifespan
    return ctx


def _batch_ok():
    return {"replies": []}


def _paragraph(text, start_index):
    """Build a paragraph element with text run that has startIndex."""
    end_index = start_index + len(text)
    return {
        "paragraph": {
            "elements": [
                {
                    "startIndex": start_index,
                    "endIndex": end_index,
                    "textRun": {"content": text},
                }
            ],
            "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
        },
        "startIndex": start_index,
        "endIndex": end_index,
    }


def _table_with_indices(rows_data, start_index):
    """Build a table element with per-cell startIndex/endIndex.

    ``rows_data``: list of lists of strings, each ending with ``\\n``.
    Returns a realistic structural element with index gaps for
    table/row/cell structural overhead.
    """
    table_rows = []
    idx = start_index + 1  # Table structural overhead

    for row in rows_data:
        idx += 1  # Row structural overhead
        cells = []
        for cell_text in row:
            idx += 1  # Cell structural overhead
            para_start = idx
            para_end = para_start + len(cell_text)
            cells.append(
                {
                    "content": [
                        {
                            "paragraph": {
                                "elements": [
                                    {
                                        "startIndex": para_start,
                                        "endIndex": para_end,
                                        "textRun": {"content": cell_text},
                                    }
                                ],
                                "paragraphStyle": {
                                    "namedStyleType": "NORMAL_TEXT"
                                },
                            },
                            "startIndex": para_start,
                            "endIndex": para_end,
                        }
                    ]
                }
            )
            idx = para_end
        table_rows.append({"tableCells": cells})

    return {
        "table": {
            "rows": len(rows_data),
            "columns": len(rows_data[0]) if rows_data else 0,
            "tableRows": table_rows,
        },
        "startIndex": start_index,
        "endIndex": idx,
    }


def _doc_with_table():
    """Standard test document: paragraph + 2x2 table + paragraph.

    Layout (approximate indices):
      [1..13]  "Hello World\\n"
      [13..X]  Table:
                 [0,0] "Cell A\\n"  (starts ~16)
                 [0,1] "Cell B\\n"  (starts ~24)
                 [1,0] "Cell C\\n"  (starts ~33)
                 [1,1] "Cell D\\n"  (starts ~41)
      [X..]    "After table\\n"
    """
    para1 = _paragraph("Hello World\n", 1)
    table = _table_with_indices(
        [["Cell A\n", "Cell B\n"], ["Cell C\n", "Cell D\n"]],
        start_index=13,
    )
    after_idx = table["endIndex"]
    para2 = _paragraph("After table\n", after_idx)
    return {
        "documentId": "doc123",
        "title": "Test Doc",
        "body": {"content": [para1, table, para2]},
    }


# ---------------------------------------------------------------------------
# _extract_text_with_positions
# ---------------------------------------------------------------------------


class TestExtractTextWithPositions:
    """Index-aware text extraction."""

    def test_simple_paragraph(self):
        elements = [_paragraph("Hello\n", 1)]
        text, segs = _extract_text_with_positions(elements)
        assert text == "Hello\n"
        assert len(segs) == 1
        assert segs[0] == (0, 1, 6)  # (text_offset, doc_index, length)

    def test_paragraph_plus_table(self):
        doc = _doc_with_table()
        content = doc["body"]["content"]
        text, segs = _extract_text_with_positions(content)

        # Flattened text should contain all content
        assert "Hello World" in text
        assert "Cell A" in text
        assert "Cell D" in text
        assert "After table" in text

        # First paragraph: text starts at offset 0, doc index 1
        assert segs[0] == (0, 1, 12)  # "Hello World\n"

        # Cell text should map to doc indices > 13 (table start)
        # due to structural overhead
        cell_a_seg = segs[1]  # "Cell A\n"
        assert cell_a_seg[1] > 13  # doc_index > table start

    def test_table_text_offsets_differ_from_doc_indices(self):
        """The key bug: text offset != doc index for table content."""
        doc = _doc_with_table()
        content = doc["body"]["content"]
        text, segs = _extract_text_with_positions(content)

        # Find "Cell A" in flattened text
        cell_a_pos = text.index("Cell A")

        # With old code: doc_index = 1 + cell_a_pos (WRONG)
        wrong_index = 1 + cell_a_pos

        # With new code: mapped doc index
        correct_index = _text_pos_to_doc_index(segs, cell_a_pos)

        assert correct_index is not None
        assert correct_index != wrong_index
        assert correct_index > 13  # Must be inside table


class TestTextRangeToDocRange:
    """Convert flattened text ranges to document index ranges."""

    def test_paragraph_range(self):
        elements = [_paragraph("Hello World\n", 1)]
        _text, segs = _extract_text_with_positions(elements)

        # "World" is at text[6:11], should map to doc[7:12]
        ds, de = _text_range_to_doc_range(segs, 6, 11)
        assert ds == 7
        assert de == 12

    def test_table_cell_range(self):
        doc = _doc_with_table()
        content = doc["body"]["content"]
        text, segs = _extract_text_with_positions(content)

        # Find "Cell A" and map to doc range
        start = text.index("Cell A")
        end = start + len("Cell A")
        ds, de = _text_range_to_doc_range(segs, start, end)

        assert ds is not None
        assert de is not None
        assert ds > 13  # Inside table
        assert de - ds == len("Cell A")

    def test_unmappable_range_returns_none(self):
        # Empty segments
        ds, de = _text_range_to_doc_range([], 0, 5)
        assert ds is None
        assert de is None


# ---------------------------------------------------------------------------
# _find_table_element / _get_cell_content_range
# ---------------------------------------------------------------------------


class TestFindTableElement:
    """Locate table elements in document content."""

    def test_finds_by_start_index(self):
        doc = _doc_with_table()
        content = doc["body"]["content"]
        elem = _find_table_element(content, 13)
        assert elem is not None
        assert "table" in elem

    def test_returns_none_for_wrong_index(self):
        doc = _doc_with_table()
        content = doc["body"]["content"]
        assert _find_table_element(content, 999) is None


class TestGetCellContentRange:
    """Extract cell content index range."""

    def test_valid_cell(self):
        doc = _doc_with_table()
        table_elem = doc["body"]["content"][1]  # The table
        start, end, text = _get_cell_content_range(table_elem, 0, 0)
        assert start is not None
        assert end is not None
        assert "Cell A" in text

    def test_row_out_of_bounds(self):
        doc = _doc_with_table()
        table_elem = doc["body"]["content"][1]
        start, end, text = _get_cell_content_range(table_elem, 99, 0)
        assert start is None

    def test_column_out_of_bounds(self):
        doc = _doc_with_table()
        table_elem = doc["body"]["content"][1]
        start, end, text = _get_cell_content_range(table_elem, 0, 99)
        assert start is None


# ---------------------------------------------------------------------------
# update_table_cell_content
# ---------------------------------------------------------------------------


class TestUpdateTableCellContentValidation:
    """Input validation for update_table_cell_content."""

    def test_empty_document_id(self):
        result = update_table_cell_content(
            "", 13, 0, 0, "new", ctx=_mock_ctx()
        )
        assert "error" in result

    def test_table_not_found(self):
        svc = MagicMock()
        svc.documents().get().execute.return_value = _doc_with_table()
        result = update_table_cell_content(
            "doc123", 999, 0, 0, "new", ctx=_mock_ctx(docs_service=svc)
        )
        assert "error" in result
        assert "No table found" in result["error"]

    def test_cell_out_of_bounds(self):
        svc = MagicMock()
        svc.documents().get().execute.return_value = _doc_with_table()
        result = update_table_cell_content(
            "doc123", 13, 99, 0, "new", ctx=_mock_ctx(docs_service=svc)
        )
        assert "error" in result
        assert "not found" in result["error"]

    def test_empty_find_text_error(self):
        svc = MagicMock()
        svc.documents().get().execute.return_value = _doc_with_table()
        result = update_table_cell_content(
            "doc123", 13, 0, 0, "new", find_text="",
            ctx=_mock_ctx(docs_service=svc),
        )
        assert "error" in result
        assert "empty" in result["error"]


class TestUpdateTableCellContentFullReplace:
    """Full cell content replacement."""

    def test_replaces_entire_cell(self):
        svc = MagicMock()
        svc.documents().get().execute.return_value = _doc_with_table()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = update_table_cell_content(
            "doc123", 13, 0, 0, "New Content", ctx=ctx
        )

        assert result["replaced"] is True
        assert result["replacementText"] == "New Content"
        assert result["cell"] == {"row": 0, "column": 0}

    def test_sends_delete_and_insert_requests(self):
        svc = MagicMock()
        svc.documents().get().execute.return_value = _doc_with_table()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        update_table_cell_content("doc123", 13, 0, 0, "New", ctx=ctx)

        # Verify batchUpdate was called
        batch_calls = svc.documents().batchUpdate.call_args_list
        assert len(batch_calls) > 0

        # Extract the requests from the batch call
        body = svc.documents().batchUpdate.call_args
        requests = body.kwargs.get("body", body[1].get("body", {})).get(
            "requests", []
        )

        # Should have deleteContentRange + insertText
        req_types = [list(r.keys())[0] for r in requests]
        assert "deleteContentRange" in req_types
        assert "insertText" in req_types

    def test_delete_preserves_trailing_newline(self):
        """The delete range should NOT include the cell's trailing \\n."""
        svc = MagicMock()
        doc = _doc_with_table()
        svc.documents().get().execute.return_value = doc
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        # Get expected cell range
        table_elem = doc["body"]["content"][1]
        c_start, c_end, _ = _get_cell_content_range(table_elem, 0, 0)

        update_table_cell_content("doc123", 13, 0, 0, "X", ctx=ctx)

        body = svc.documents().batchUpdate.call_args
        requests = body.kwargs.get("body", body[1].get("body", {})).get(
            "requests", []
        )
        delete_req = [r for r in requests if "deleteContentRange" in r][0]
        rng = delete_req["deleteContentRange"]["range"]

        # Should delete up to c_end - 1 (preserve \n)
        assert rng["startIndex"] == c_start
        assert rng["endIndex"] == c_end - 1


class TestUpdateTableCellContentPartialReplace:
    """Partial find-and-replace within a cell."""

    def test_finds_and_replaces_within_cell(self):
        svc = MagicMock()
        svc.documents().get().execute.return_value = _doc_with_table()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = update_table_cell_content(
            "doc123", 13, 0, 0, "Alpha",
            find_text="Cell A", ctx=ctx,
        )

        assert result["replaced"] is True
        assert result["findText"] == "Cell A"
        assert result["replacementText"] == "Alpha"

    def test_find_not_found_in_cell(self):
        svc = MagicMock()
        svc.documents().get().execute.return_value = _doc_with_table()
        ctx = _mock_ctx(docs_service=svc)

        result = update_table_cell_content(
            "doc123", 13, 0, 0, "New",
            find_text="NONEXISTENT", ctx=ctx,
        )

        assert result.get("found") is False

    def test_case_insensitive_find(self):
        svc = MagicMock()
        svc.documents().get().execute.return_value = _doc_with_table()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = update_table_cell_content(
            "doc123", 13, 0, 0, "ALPHA",
            find_text="cell a", match_case=False, ctx=ctx,
        )

        assert result["replaced"] is True

    def test_partial_replace_targets_correct_indices(self):
        """The delete+insert should target within the cell, not body."""
        svc = MagicMock()
        doc = _doc_with_table()
        svc.documents().get().execute.return_value = doc
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        update_table_cell_content(
            "doc123", 13, 0, 0, "X",
            find_text="Cell A", ctx=ctx,
        )

        body = svc.documents().batchUpdate.call_args
        requests = body.kwargs.get("body", body[1].get("body", {})).get(
            "requests", []
        )

        delete_req = [r for r in requests if "deleteContentRange" in r][0]
        rng = delete_req["deleteContentRange"]["range"]

        # The delete range must be inside the table (>13)
        assert rng["startIndex"] > 13
        assert rng["endIndex"] > 13


class TestUpdateTableCellContentApiError:
    """API error handling."""

    def test_api_error_propagated(self):
        svc = MagicMock()
        svc.documents().get().execute.return_value = _doc_with_table()
        svc.documents().batchUpdate().execute.side_effect = Exception("API")
        ctx = _mock_ctx(docs_service=svc)

        result = update_table_cell_content(
            "doc123", 13, 0, 0, "New", ctx=ctx
        )
        assert "error" in result


# ---------------------------------------------------------------------------
# get_tables — cell indices enhancement
# ---------------------------------------------------------------------------


class TestGetTablesCellIndices:
    """get_tables should now include cellIndices."""

    def test_returns_cell_indices(self):
        svc = MagicMock()
        svc.documents().get().execute.return_value = _doc_with_table()
        ctx = _mock_ctx(docs_service=svc)

        result = get_tables("doc123", ctx=ctx)
        assert result["tableCount"] == 1

        table = result["tables"][0]
        assert "cellIndices" in table
        assert len(table["cellIndices"]) == 2  # 2 rows
        assert len(table["cellIndices"][0]) == 2  # 2 columns

        # Each cell index entry should have startIndex/endIndex
        cell_00 = table["cellIndices"][0][0]
        assert cell_00["startIndex"] is not None
        assert cell_00["endIndex"] is not None
        assert cell_00["startIndex"] > 13  # Inside table

    def test_cell_indices_match_actual_content(self):
        """cellIndices should match the actual cell content positions."""
        svc = MagicMock()
        doc = _doc_with_table()
        svc.documents().get().execute.return_value = doc
        ctx = _mock_ctx(docs_service=svc)

        result = get_tables("doc123", ctx=ctx)
        table = result["tables"][0]

        # Verify against raw document structure
        table_elem = doc["body"]["content"][1]
        for r, row in enumerate(table_elem["table"]["tableRows"]):
            for c, cell in enumerate(row["tableCells"]):
                expected_start = cell["content"][0].get("startIndex")
                expected_end = cell["content"][-1].get("endIndex")
                actual = table["cellIndices"][r][c]
                assert actual["startIndex"] == expected_start
                assert actual["endIndex"] == expected_end


# ---------------------------------------------------------------------------
# search_document — documentIndex enhancement
# ---------------------------------------------------------------------------


class TestSearchDocumentIndex:
    """search_document should include documentIndex for each match."""

    def test_paragraph_match_has_document_index(self):
        svc = MagicMock()
        svc.documents().get().execute.return_value = _doc_with_table()
        ctx = _mock_ctx(docs_service=svc)

        result = search_document("doc123", "Hello", ctx=ctx)
        assert result["matchCount"] >= 1
        match = result["matches"][0]
        assert "documentIndex" in match
        # "Hello" starts at doc index 1
        assert match["documentIndex"] == 1

    def test_table_match_has_correct_document_index(self):
        """Key test: table content documentIndex must differ from position."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = _doc_with_table()
        ctx = _mock_ctx(docs_service=svc)

        result = search_document("doc123", "Cell A", ctx=ctx)
        assert result["matchCount"] >= 1

        match = result["matches"][0]
        assert "documentIndex" in match
        assert "documentEndIndex" in match

        # documentIndex must be > 13 (inside table), not position+1
        assert match["documentIndex"] > 13

        # position is the flattened text offset (old behavior, preserved)
        assert match["position"] != match["documentIndex"]


# ---------------------------------------------------------------------------
# replace_first_text — table-safe fix
# ---------------------------------------------------------------------------


class TestReplaceFirstTextTableSafe:
    """replace_first_text should use correct indices for table content."""

    def test_replace_in_paragraph_still_works(self):
        svc = MagicMock()
        svc.documents().get().execute.return_value = _doc_with_table()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = replace_first_text("doc123", "Hello", "Hi", ctx=ctx)
        assert result["replacedAt"] == 1  # Correct doc index

    def test_replace_in_table_uses_mapped_indices(self):
        """CRITICAL: replacing text in a table cell must target correct indices."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = _doc_with_table()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = replace_first_text("doc123", "Cell A", "Alpha", ctx=ctx)

        # replacedAt must be inside the table (>13), not 1 + text_offset
        assert result["replacedAt"] > 13

        # Verify the batchUpdate request uses correct indices
        body = svc.documents().batchUpdate.call_args
        requests = body.kwargs.get("body", body[1].get("body", {})).get(
            "requests", []
        )

        delete_req = [r for r in requests if "deleteContentRange" in r][0]
        rng = delete_req["deleteContentRange"]["range"]
        assert rng["startIndex"] > 13
        assert rng["endIndex"] > 13


# ---------------------------------------------------------------------------
# replace_text_in_range — table-safe fix
# ---------------------------------------------------------------------------


class TestReplaceTextInRangeTableSafe:
    """replace_text_in_range should use mapped document indices."""

    def test_replace_in_table_range(self):
        """Replace within a table's index range should work."""
        svc = MagicMock()
        doc = _doc_with_table()
        svc.documents().get().execute.return_value = doc
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        # Use the table's actual index range
        table_start = doc["body"]["content"][1]["startIndex"]
        table_end = doc["body"]["content"][1]["endIndex"]

        result = replace_text_in_range(
            "doc123", "Cell A", "Alpha",
            start_index=table_start, end_index=table_end, ctx=ctx,
        )

        assert result["occurrencesReplaced"] == 1

    def test_range_excludes_matches_outside(self):
        """Matches outside the specified range should not be replaced."""
        svc = MagicMock()
        doc = _doc_with_table()
        svc.documents().get().execute.return_value = doc
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        # Use range that only covers the paragraph before the table
        result = replace_text_in_range(
            "doc123", "Cell A", "Alpha",
            start_index=1, end_index=13, ctx=ctx,
        )

        assert result["occurrencesReplaced"] == 0
