"""Tests for batch table operations: populate_table and insert_populated_table."""

from unittest.mock import MagicMock, call

from mcp_google_workspace.tools.docs.table import (
    MAX_POPULATE_CELLS,
    _get_all_cell_start_indices,
    insert_populated_table,
    populate_table,
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


def _table_with_indices(rows_data, start_index):
    """Build a table element with per-cell startIndex/endIndex.

    ``rows_data``: list of lists of strings, each ending with ``\\n``.
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


def _paragraph(text, start_index):
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


def _doc_with_3x3_table():
    """Document with paragraph + 3x3 table."""
    para1 = _paragraph("Header\n", 1)
    table = _table_with_indices(
        [
            ["\n", "\n", "\n"],  # Empty row (will be populated)
            ["\n", "\n", "\n"],
            ["\n", "\n", "\n"],
        ],
        start_index=8,
    )
    return {
        "documentId": "doc_3x3",
        "title": "Test 3x3",
        "body": {"content": [para1, table]},
    }


def _doc_with_2x2_table():
    """Document with paragraph + 2x2 table with existing content."""
    para1 = _paragraph("Intro\n", 1)
    table = _table_with_indices(
        [["A\n", "B\n"], ["C\n", "D\n"]],
        start_index=7,
    )
    return {
        "documentId": "doc_2x2",
        "title": "Test 2x2",
        "body": {"content": [para1, table]},
    }


# ---------------------------------------------------------------------------
# _get_all_cell_start_indices
# ---------------------------------------------------------------------------


class TestGetAllCellStartIndices:
    def test_extracts_indices_for_all_cells(self):
        table_elem = _table_with_indices(
            [["A\n", "B\n"], ["C\n", "D\n"]], start_index=10
        )
        indices = _get_all_cell_start_indices(table_elem)
        assert len(indices) == 2
        assert len(indices[0]) == 2
        assert len(indices[1]) == 2
        # All should be non-None and inside the table
        for row in indices:
            for idx in row:
                assert idx is not None
                assert idx > 10

    def test_empty_table(self):
        table_elem = {"table": {"tableRows": []}}
        indices = _get_all_cell_start_indices(table_elem)
        assert indices == []

    def test_cell_without_content(self):
        """Cell with no content should yield None."""
        table_elem = {
            "table": {
                "tableRows": [
                    {"tableCells": [{"content": []}]},
                ]
            }
        }
        indices = _get_all_cell_start_indices(table_elem)
        assert indices == [[None]]


# ---------------------------------------------------------------------------
# populate_table
# ---------------------------------------------------------------------------


class TestPopulateTableValidation:
    def test_empty_document_id(self):
        result = populate_table("", 10, [["x"]], ctx=_mock_ctx())
        assert "error" in result

    def test_empty_data(self):
        result = populate_table("doc1", 10, [], ctx=_mock_ctx())
        assert "error" in result

    def test_too_many_cells(self):
        # Create data that exceeds MAX_POPULATE_CELLS
        huge_data = [["x"] * 100 for _ in range(30)]
        result = populate_table("doc1", 10, huge_data, ctx=_mock_ctx())
        assert "error" in result
        assert "Too many cells" in result["error"]

    def test_table_not_found(self):
        svc = MagicMock()
        doc = _doc_with_2x2_table()
        svc.documents().get().execute.return_value = doc
        ctx = _mock_ctx(docs_service=svc)

        result = populate_table("doc1", 999, [["x"]], ctx=ctx)
        assert "error" in result
        assert "No table found" in result["error"]


class TestPopulateTableSuccess:
    def test_populates_all_cells(self):
        svc = MagicMock()
        doc = _doc_with_3x3_table()
        svc.documents().get().execute.return_value = doc
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        data = [
            ["H1", "H2", "H3"],
            ["A1", "A2", "A3"],
            ["B1", "B2", "B3"],
        ]
        result = populate_table("doc_3x3", 8, data, ctx=ctx)

        assert "error" not in result
        assert result["cellsWritten"] == 9
        assert result["tableSize"] == {"rows": 3, "columns": 3}

    def test_skips_empty_strings(self):
        svc = MagicMock()
        doc = _doc_with_3x3_table()
        svc.documents().get().execute.return_value = doc
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        data = [
            ["H1", "", "H3"],
            ["", "A2", ""],
            ["B1", "", "B3"],
        ]
        result = populate_table("doc_3x3", 8, data, ctx=ctx)

        assert "error" not in result
        assert result["cellsWritten"] == 5  # Only non-empty cells

    def test_all_empty_returns_zero_written(self):
        svc = MagicMock()
        doc = _doc_with_3x3_table()
        svc.documents().get().execute.return_value = doc
        ctx = _mock_ctx(docs_service=svc)

        data = [["", ""], ["", ""]]
        result = populate_table("doc_3x3", 8, data, ctx=ctx)

        assert result["cellsWritten"] == 0

    def test_partial_data_smaller_than_table(self):
        """Data with fewer rows/cols than table should work fine."""
        svc = MagicMock()
        doc = _doc_with_3x3_table()
        svc.documents().get().execute.return_value = doc
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        data = [["Only"]]  # 1x1 data for 3x3 table
        result = populate_table("doc_3x3", 8, data, ctx=ctx)

        assert "error" not in result
        assert result["cellsWritten"] == 1

    def test_data_larger_than_table_ignores_excess(self):
        """Data with more rows/cols than table ignores overflow."""
        svc = MagicMock()
        doc = _doc_with_2x2_table()
        svc.documents().get().execute.return_value = doc
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        data = [
            ["a", "b", "c", "d"],  # 4 cols, table has 2
            ["e", "f", "g", "h"],
            ["i", "j", "k", "l"],  # 3 rows, table has 2
        ]
        result = populate_table("doc_2x2", 7, data, ctx=ctx)

        assert "error" not in result
        assert result["cellsWritten"] == 4  # Only 2x2 fits

    def test_requests_in_reverse_order(self):
        """InsertText requests must be in reverse order to avoid index shifts."""
        svc = MagicMock()
        doc = _doc_with_2x2_table()
        svc.documents().get().execute.return_value = doc
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        data = [["R0C0", "R0C1"], ["R1C0", "R1C1"]]
        populate_table("doc_2x2", 7, data, ctx=ctx)

        # Extract requests from batchUpdate call
        batch_call = svc.documents().batchUpdate.call_args
        body = batch_call.kwargs.get("body", batch_call[1].get("body", {}))
        requests = body.get("requests", [])

        # All should be insertText
        assert all("insertText" in r for r in requests)

        # Indices should be in descending order (reverse)
        indices = [
            r["insertText"]["location"]["index"] for r in requests
        ]
        assert indices == sorted(indices, reverse=True)

    def test_api_error_propagated(self):
        svc = MagicMock()
        doc = _doc_with_3x3_table()
        svc.documents().get().execute.return_value = doc
        svc.documents().batchUpdate().execute.side_effect = Exception("API fail")
        ctx = _mock_ctx(docs_service=svc)

        result = populate_table("doc_3x3", 8, [["x"]], ctx=ctx)
        assert "error" in result


# ---------------------------------------------------------------------------
# insert_populated_table
# ---------------------------------------------------------------------------


class TestInsertPopulatedTableValidation:
    def test_empty_document_id(self):
        result = insert_populated_table("", [["x"]], ctx=_mock_ctx())
        assert "error" in result

    def test_empty_data(self):
        result = insert_populated_table("doc1", [], ctx=_mock_ctx())
        assert "error" in result

    def test_all_empty_rows(self):
        result = insert_populated_table("doc1", [[]], ctx=_mock_ctx())
        assert "error" in result
        assert "non-empty" in result["error"]

    def test_too_many_rows(self):
        data = [["x"]] * 101  # MAX_TABLE_ROWS = 100
        result = insert_populated_table("doc1", data, ctx=_mock_ctx())
        assert "error" in result

    def test_too_many_columns(self):
        data = [["x"] * 27]  # MAX_TABLE_COLUMNS = 26
        result = insert_populated_table("doc1", data, ctx=_mock_ctx())
        assert "error" in result


class TestInsertPopulatedTableSuccess:
    def _setup_svc(self, table_start_index=1):
        """Set up mock service that returns a table after insert."""
        svc = MagicMock()

        # First batchUpdate: insertTable succeeds
        svc.documents().batchUpdate().execute.return_value = _batch_ok()

        # After inserting, reading the doc returns the new table
        table = _table_with_indices(
            [["\n", "\n"], ["\n", "\n"], ["\n", "\n"]],
            start_index=table_start_index,
        )
        para = _paragraph("", 1) if table_start_index > 1 else None
        content = [para, table] if para else [table]
        doc = {
            "documentId": "doc1",
            "title": "Test",
            "body": {"content": content},
        }
        svc.documents().get().execute.return_value = doc
        return svc

    def test_creates_and_fills_table(self):
        svc = self._setup_svc(table_start_index=1)
        ctx = _mock_ctx(docs_service=svc)

        data = [
            ["Name", "Age"],
            ["Alice", "30"],
            ["Bob", "25"],
        ]
        result = insert_populated_table("doc1", data, index=1, ctx=ctx)

        assert "error" not in result
        assert result["rows"] == 3
        assert result["columns"] == 2
        assert result["cellsWritten"] == 6

    def test_ragged_rows_use_max_columns(self):
        """Rows with different lengths: column count = max row length."""
        svc = self._setup_svc(table_start_index=1)
        ctx = _mock_ctx(docs_service=svc)

        data = [
            ["A", "B"],
            ["C"],  # Shorter row
        ]
        result = insert_populated_table("doc1", data, index=1, ctx=ctx)

        assert "error" not in result
        assert result["columns"] == 2  # Inferred from longest row

    def test_insert_table_api_error(self):
        """If insertTable fails, error is returned immediately."""
        svc = MagicMock()
        svc.documents().batchUpdate().execute.side_effect = Exception("Insert fail")
        ctx = _mock_ctx(docs_service=svc)

        result = insert_populated_table("doc1", [["x"]], ctx=ctx)
        assert "error" in result

    def test_table_not_found_after_insert(self):
        """If table can't be located after insert, warning is returned."""
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        # Return empty doc (no table elements)
        svc.documents().get().execute.return_value = {
            "documentId": "doc1",
            "title": "Test",
            "body": {"content": [_paragraph("text\n", 1)]},
        }
        ctx = _mock_ctx(docs_service=svc)

        result = insert_populated_table("doc1", [["x"]], ctx=ctx)
        assert "warning" in result
        assert result["cellsWritten"] == 0

    def test_population_failure_returns_warning(self):
        """If table is created but population batchUpdate fails."""
        svc = MagicMock()

        table = _table_with_indices([["\n"]], start_index=1)
        doc = {
            "documentId": "doc1",
            "title": "Test",
            "body": {"content": [table]},
        }
        svc.documents().get().execute.return_value = doc

        # First batchUpdate (insertTable) succeeds,
        # second batchUpdate (populate) fails
        svc.documents().batchUpdate().execute.side_effect = [
            _batch_ok(),
            Exception("Populate fail"),
        ]
        ctx = _mock_ctx(docs_service=svc)

        result = insert_populated_table("doc1", [["data"]], ctx=ctx)
        assert "warning" in result
        assert "population failed" in result["warning"]

    def test_default_index_is_1(self):
        svc = self._setup_svc(table_start_index=1)
        ctx = _mock_ctx(docs_service=svc)

        result = insert_populated_table("doc1", [["x", "y"]], ctx=ctx)

        assert "error" not in result
        assert result["insertedAt"] == 1


# ---------------------------------------------------------------------------
# Module constant sanity check
# ---------------------------------------------------------------------------


class TestConstants:
    def test_max_populate_cells_reasonable(self):
        assert MAX_POPULATE_CELLS >= 100  # At least 10x10
        assert MAX_POPULATE_CELLS <= 10000  # Not absurdly large
