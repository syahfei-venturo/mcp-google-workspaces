"""Tests for Google Docs table operation tools with mocked API services."""

from unittest.mock import MagicMock

from mcp_google_workspace.tools.docs.table import (
    delete_table_column,
    delete_table_row,
    insert_table_column,
    insert_table_row,
    merge_table_cells,
    unmerge_table_cells,
    update_table_cell_style,
)


def _mock_ctx(docs_service=None):
    """Build a mock Context with lifespan_context services."""
    ctx = MagicMock()
    lifespan = MagicMock()
    lifespan.docs_service = docs_service or MagicMock()
    ctx.request_context.lifespan_context = lifespan
    return ctx


def _batch_ok():
    """Standard successful batchUpdate response."""
    return {"replies": []}


class TestUpdateTableCellStyle:
    """Tests for update_table_cell_style."""

    def test_sets_background_color(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = update_table_cell_style(
            "doc1",
            table_start_index=5,
            row_index=0,
            column_index=0,
            background_color={"red": 1.0, "green": 0.0, "blue": 0.0},
            ctx=ctx,
        )
        assert "backgroundColor" in result["appliedStyles"]

    def test_sets_padding(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = update_table_cell_style(
            "doc1",
            table_start_index=5,
            row_index=0,
            column_index=1,
            padding_top=4.0,
            padding_bottom=4.0,
            padding_left=6.0,
            padding_right=6.0,
            ctx=ctx,
        )
        assert "paddingTop" in result["appliedStyles"]
        assert "paddingBottom" in result["appliedStyles"]
        assert "paddingLeft" in result["appliedStyles"]
        assert "paddingRight" in result["appliedStyles"]

    def test_sets_border(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = update_table_cell_style(
            "doc1",
            table_start_index=5,
            row_index=0,
            column_index=0,
            border_width=1.0,
            border_dash_style="SOLID",
            ctx=ctx,
        )
        assert "borderTop" in result["appliedStyles"]
        assert "borderBottom" in result["appliedStyles"]

    def test_sets_content_alignment(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = update_table_cell_style(
            "doc1",
            table_start_index=5,
            row_index=0,
            column_index=0,
            content_alignment="MIDDLE",
            ctx=ctx,
        )
        assert "contentAlignment" in result["appliedStyles"]

    def test_invalid_content_alignment(self):
        ctx = _mock_ctx()
        result = update_table_cell_style(
            "doc1",
            table_start_index=5,
            row_index=0,
            column_index=0,
            content_alignment="INVALID",
            ctx=ctx,
        )
        assert "error" in result

    def test_invalid_dash_style(self):
        ctx = _mock_ctx()
        result = update_table_cell_style(
            "doc1",
            table_start_index=5,
            row_index=0,
            column_index=0,
            border_dash_style="WAVY",
            ctx=ctx,
        )
        assert "error" in result

    def test_no_styles_error(self):
        ctx = _mock_ctx()
        result = update_table_cell_style(
            "doc1",
            table_start_index=5,
            row_index=0,
            column_index=0,
            ctx=ctx,
        )
        assert "error" in result

    def test_empty_document_id(self):
        ctx = _mock_ctx()
        result = update_table_cell_style(
            "",
            table_start_index=5,
            row_index=0,
            column_index=0,
            background_color={"red": 1.0},
            ctx=ctx,
        )
        assert "error" in result

    def test_negative_padding(self):
        ctx = _mock_ctx()
        result = update_table_cell_style(
            "doc1",
            table_start_index=5,
            row_index=0,
            column_index=0,
            padding_top=-1,
            ctx=ctx,
        )
        assert "error" in result
        assert "padding_top" in result["error"]

    def test_padding_exceeds_max(self):
        ctx = _mock_ctx()
        result = update_table_cell_style(
            "doc1",
            table_start_index=5,
            row_index=0,
            column_index=0,
            padding_left=145,
            ctx=ctx,
        )
        assert "error" in result
        assert "144" in result["error"]

    def test_negative_border_width(self):
        ctx = _mock_ctx()
        result = update_table_cell_style(
            "doc1",
            table_start_index=5,
            row_index=0,
            column_index=0,
            border_width=-1,
            ctx=ctx,
        )
        assert "error" in result
        assert "border_width" in result["error"]

    def test_border_width_exceeds_max(self):
        ctx = _mock_ctx()
        result = update_table_cell_style(
            "doc1",
            table_start_index=5,
            row_index=0,
            column_index=0,
            border_width=25,
            ctx=ctx,
        )
        assert "error" in result
        assert "24" in result["error"]

    def test_api_error_propagated(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.side_effect = Exception("API down")
        ctx = _mock_ctx(docs_service=svc)

        result = update_table_cell_style(
            "doc1",
            table_start_index=5,
            row_index=0,
            column_index=0,
            background_color={"red": 1.0},
            ctx=ctx,
        )
        assert "error" in result


class TestInsertTableRow:
    """Tests for insert_table_row."""

    def test_inserts_below(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = insert_table_row(
            "doc1", table_start_index=5, row_index=0, insert_below=True, ctx=ctx
        )
        assert result["documentId"] == "doc1"
        assert result["insertedBelow"] is True
        assert result["referenceRow"] == 0

    def test_inserts_above(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = insert_table_row(
            "doc1", table_start_index=5, row_index=2, insert_below=False, ctx=ctx
        )
        assert result["insertedBelow"] is False
        assert result["referenceRow"] == 2

    def test_empty_document_id(self):
        ctx = _mock_ctx()
        result = insert_table_row("", table_start_index=5, row_index=0, ctx=ctx)
        assert "error" in result


class TestInsertTableColumn:
    """Tests for insert_table_column."""

    def test_inserts_right(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = insert_table_column(
            "doc1", table_start_index=5, column_index=1, insert_right=True, ctx=ctx
        )
        assert result["insertedRight"] is True
        assert result["referenceColumn"] == 1

    def test_inserts_left(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = insert_table_column(
            "doc1", table_start_index=5, column_index=0, insert_right=False, ctx=ctx
        )
        assert result["insertedRight"] is False

    def test_empty_document_id(self):
        ctx = _mock_ctx()
        result = insert_table_column("", table_start_index=5, column_index=0, ctx=ctx)
        assert "error" in result


class TestDeleteTableRow:
    """Tests for delete_table_row."""

    def test_deletes_row(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = delete_table_row("doc1", table_start_index=5, row_index=1, ctx=ctx)
        assert result["deletedRow"] == 1

    def test_empty_document_id(self):
        ctx = _mock_ctx()
        result = delete_table_row("", table_start_index=5, row_index=0, ctx=ctx)
        assert "error" in result


class TestDeleteTableColumn:
    """Tests for delete_table_column."""

    def test_deletes_column(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = delete_table_column(
            "doc1", table_start_index=5, column_index=2, ctx=ctx
        )
        assert result["deletedColumn"] == 2

    def test_empty_document_id(self):
        ctx = _mock_ctx()
        result = delete_table_column("", table_start_index=5, column_index=0, ctx=ctx)
        assert "error" in result


class TestMergeTableCells:
    """Tests for merge_table_cells."""

    def test_merges_range(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = merge_table_cells(
            "doc1",
            table_start_index=5,
            row_index=0,
            column_index=0,
            row_span=2,
            column_span=3,
            ctx=ctx,
        )
        assert result["mergedRange"]["rowSpan"] == 2
        assert result["mergedRange"]["columnSpan"] == 3

    def test_invalid_span(self):
        ctx = _mock_ctx()
        result = merge_table_cells(
            "doc1",
            table_start_index=5,
            row_index=0,
            column_index=0,
            row_span=0,
            column_span=2,
            ctx=ctx,
        )
        assert "error" in result

    def test_row_span_exceeds_max(self):
        ctx = _mock_ctx()
        result = merge_table_cells(
            "doc1",
            table_start_index=5,
            row_index=0,
            column_index=0,
            row_span=101,
            column_span=1,
            ctx=ctx,
        )
        assert "error" in result
        assert "100" in result["error"]

    def test_column_span_exceeds_max(self):
        ctx = _mock_ctx()
        result = merge_table_cells(
            "doc1",
            table_start_index=5,
            row_index=0,
            column_index=0,
            row_span=1,
            column_span=27,
            ctx=ctx,
        )
        assert "error" in result
        assert "26" in result["error"]

    def test_api_error_propagated(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.side_effect = Exception("API down")
        ctx = _mock_ctx(docs_service=svc)

        result = merge_table_cells(
            "doc1",
            table_start_index=5,
            row_index=0,
            column_index=0,
            row_span=2,
            column_span=2,
            ctx=ctx,
        )
        assert "error" in result

    def test_empty_document_id(self):
        ctx = _mock_ctx()
        result = merge_table_cells(
            "",
            table_start_index=5,
            row_index=0,
            column_index=0,
            row_span=1,
            column_span=1,
            ctx=ctx,
        )
        assert "error" in result


class TestUnmergeTableCells:
    """Tests for unmerge_table_cells."""

    def test_unmerges_range(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = unmerge_table_cells(
            "doc1",
            table_start_index=5,
            row_index=0,
            column_index=0,
            row_span=2,
            column_span=2,
            ctx=ctx,
        )
        assert result["unmergedRange"]["rowSpan"] == 2
        assert result["unmergedRange"]["columnSpan"] == 2

    def test_invalid_span(self):
        ctx = _mock_ctx()
        result = unmerge_table_cells(
            "doc1",
            table_start_index=5,
            row_index=0,
            column_index=0,
            row_span=1,
            column_span=0,
            ctx=ctx,
        )
        assert "error" in result

    def test_row_span_exceeds_max(self):
        ctx = _mock_ctx()
        result = unmerge_table_cells(
            "doc1",
            table_start_index=5,
            row_index=0,
            column_index=0,
            row_span=101,
            column_span=1,
            ctx=ctx,
        )
        assert "error" in result

    def test_column_span_exceeds_max(self):
        ctx = _mock_ctx()
        result = unmerge_table_cells(
            "doc1",
            table_start_index=5,
            row_index=0,
            column_index=0,
            row_span=1,
            column_span=27,
            ctx=ctx,
        )
        assert "error" in result

    def test_api_error_propagated(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.side_effect = Exception("API down")
        ctx = _mock_ctx(docs_service=svc)

        result = unmerge_table_cells(
            "doc1",
            table_start_index=5,
            row_index=0,
            column_index=0,
            row_span=2,
            column_span=2,
            ctx=ctx,
        )
        assert "error" in result

    def test_empty_document_id(self):
        ctx = _mock_ctx()
        result = unmerge_table_cells(
            "",
            table_start_index=5,
            row_index=0,
            column_index=0,
            row_span=1,
            column_span=1,
            ctx=ctx,
        )
        assert "error" in result
