"""Tests for Google Docs formatting tools with mocked API services."""

from unittest.mock import MagicMock

from mcp_google_workspace.tools.docs.format import (
    batch_update_document,
    create_footnote,
    create_paragraph_bullets,
    delete_paragraph_bullets,
    insert_horizontal_rule,
    insert_inline_image,
    insert_page_break,
    insert_section_break,
    insert_table,
    update_document_style,
    update_paragraph_style,
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


class TestUpdateParagraphStyle:
    """Tests for update_paragraph_style."""

    def test_sets_heading(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = update_paragraph_style("doc1", 1, 20, named_style="HEADING_1", ctx=ctx)
        assert "namedStyleType" in result["appliedStyles"]

    def test_sets_alignment(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = update_paragraph_style("doc1", 1, 10, alignment="CENTER", ctx=ctx)
        assert "alignment" in result["appliedStyles"]

    def test_sets_spacing(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = update_paragraph_style(
            "doc1",
            1,
            50,
            line_spacing=150,
            space_above=12,
            space_below=6,
            ctx=ctx,
        )
        assert "lineSpacing" in result["appliedStyles"]
        assert "spaceAbove" in result["appliedStyles"]
        assert "spaceBelow" in result["appliedStyles"]

    def test_sets_indentation(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = update_paragraph_style(
            "doc1",
            1,
            30,
            indent_first_line=36,
            indent_start=18,
            ctx=ctx,
        )
        assert "indentFirstLine" in result["appliedStyles"]
        assert "indentStart" in result["appliedStyles"]

    def test_sets_keep_options(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = update_paragraph_style(
            "doc1", 1, 10, keep_with_next=True, keep_lines_together=True, ctx=ctx
        )
        assert "keepWithNext" in result["appliedStyles"]
        assert "keepLinesTogether" in result["appliedStyles"]

    def test_invalid_named_style(self):
        ctx = _mock_ctx()
        result = update_paragraph_style("doc1", 1, 10, named_style="INVALID", ctx=ctx)
        assert "error" in result

    def test_invalid_alignment(self):
        ctx = _mock_ctx()
        result = update_paragraph_style("doc1", 1, 10, alignment="MIDDLE", ctx=ctx)
        assert "error" in result

    def test_invalid_range(self):
        ctx = _mock_ctx()
        result = update_paragraph_style("doc1", 10, 5, named_style="TITLE", ctx=ctx)
        assert "error" in result

    def test_no_styles_error(self):
        ctx = _mock_ctx()
        result = update_paragraph_style("doc1", 1, 10, ctx=ctx)
        assert "error" in result

    def test_empty_document_id(self):
        ctx = _mock_ctx()
        result = update_paragraph_style("", 1, 10, named_style="TITLE", ctx=ctx)
        assert "error" in result

    def test_negative_line_spacing(self):
        ctx = _mock_ctx()
        result = update_paragraph_style("doc1", 1, 10, line_spacing=-1, ctx=ctx)
        assert "error" in result
        assert "line_spacing" in result["error"]

    def test_zero_line_spacing(self):
        ctx = _mock_ctx()
        result = update_paragraph_style("doc1", 1, 10, line_spacing=0, ctx=ctx)
        assert "error" in result

    def test_negative_space_above(self):
        ctx = _mock_ctx()
        result = update_paragraph_style("doc1", 1, 10, space_above=-5, ctx=ctx)
        assert "error" in result
        assert "space_above" in result["error"]

    def test_negative_space_below(self):
        ctx = _mock_ctx()
        result = update_paragraph_style("doc1", 1, 10, space_below=-1, ctx=ctx)
        assert "error" in result
        assert "space_below" in result["error"]

    def test_negative_indent(self):
        ctx = _mock_ctx()
        result = update_paragraph_style("doc1", 1, 10, indent_first_line=-10, ctx=ctx)
        assert "error" in result
        assert "indent_first_line" in result["error"]

    def test_api_error_propagated(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.side_effect = Exception("API down")
        ctx = _mock_ctx(docs_service=svc)

        result = update_paragraph_style("doc1", 1, 10, named_style="TITLE", ctx=ctx)
        assert "error" in result


class TestInsertHorizontalRule:
    """Tests for insert_horizontal_rule."""

    def test_inserts_at_index(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = insert_horizontal_rule("doc1", index=5, ctx=ctx)
        assert result["documentId"] == "doc1"
        assert result["insertedAt"] == 5

    def test_default_index(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = insert_horizontal_rule("doc1", ctx=ctx)
        assert result["insertedAt"] == 1

    def test_custom_weight(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = insert_horizontal_rule("doc1", index=3, weight=2.5, ctx=ctx)
        assert result["insertedAt"] == 3

    def test_empty_document_id(self):
        ctx = _mock_ctx()
        result = insert_horizontal_rule("", ctx=ctx)
        assert "error" in result

    def test_weight_zero(self):
        ctx = _mock_ctx()
        result = insert_horizontal_rule("doc1", weight=0, ctx=ctx)
        assert "error" in result

    def test_weight_negative(self):
        ctx = _mock_ctx()
        result = insert_horizontal_rule("doc1", weight=-1, ctx=ctx)
        assert "error" in result

    def test_weight_exceeds_max(self):
        ctx = _mock_ctx()
        result = insert_horizontal_rule("doc1", weight=51, ctx=ctx)
        assert "error" in result
        assert "50" in result["error"]

    def test_api_error_propagated(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.side_effect = Exception("API down")
        ctx = _mock_ctx(docs_service=svc)

        result = insert_horizontal_rule("doc1", ctx=ctx)
        assert "error" in result


class TestInsertPageBreak:
    """Tests for insert_page_break."""

    def test_inserts_at_index(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = insert_page_break("doc1", index=10, ctx=ctx)
        assert result["documentId"] == "doc1"
        assert result["insertedAt"] == 10

    def test_default_index(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = insert_page_break("doc1", ctx=ctx)
        assert result["insertedAt"] == 1

    def test_empty_document_id(self):
        ctx = _mock_ctx()
        result = insert_page_break("", ctx=ctx)
        assert "error" in result


class TestInsertTable:
    """Tests for insert_table."""

    def test_creates_table(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = insert_table("doc1", rows=3, columns=4, index=5, ctx=ctx)
        assert result["rows"] == 3
        assert result["columns"] == 4
        assert result["insertedAt"] == 5

    def test_minimum_size(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = insert_table("doc1", rows=1, columns=1, ctx=ctx)
        assert result["rows"] == 1
        assert result["columns"] == 1

    def test_zero_rows_error(self):
        ctx = _mock_ctx()
        result = insert_table("doc1", rows=0, columns=3, ctx=ctx)
        assert "error" in result

    def test_zero_columns_error(self):
        ctx = _mock_ctx()
        result = insert_table("doc1", rows=3, columns=0, ctx=ctx)
        assert "error" in result

    def test_exceeds_max_rows(self):
        ctx = _mock_ctx()
        result = insert_table("doc1", rows=101, columns=3, ctx=ctx)
        assert "error" in result

    def test_exceeds_max_columns(self):
        ctx = _mock_ctx()
        result = insert_table("doc1", rows=3, columns=27, ctx=ctx)
        assert "error" in result

    def test_empty_document_id(self):
        ctx = _mock_ctx()
        result = insert_table("", rows=2, columns=2, ctx=ctx)
        assert "error" in result


class TestCreateParagraphBullets:
    """Tests for create_paragraph_bullets."""

    def test_applies_bullet_list(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = create_paragraph_bullets("doc1", 1, 50, ctx=ctx)
        assert result["preset"] == "BULLET_DISC_CIRCLE_SQUARE"

    def test_applies_numbered_list(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = create_paragraph_bullets(
            "doc1", 1, 50, bullet_preset="NUMBERED_DECIMAL_ALPHA_ROMAN", ctx=ctx
        )
        assert result["preset"] == "NUMBERED_DECIMAL_ALPHA_ROMAN"

    def test_checkbox_preset(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = create_paragraph_bullets(
            "doc1", 1, 30, bullet_preset="BULLET_CHECKBOX", ctx=ctx
        )
        assert result["preset"] == "BULLET_CHECKBOX"

    def test_invalid_preset(self):
        ctx = _mock_ctx()
        result = create_paragraph_bullets(
            "doc1", 1, 10, bullet_preset="INVALID_STYLE", ctx=ctx
        )
        assert "error" in result

    def test_invalid_range(self):
        ctx = _mock_ctx()
        result = create_paragraph_bullets("doc1", 10, 5, ctx=ctx)
        assert "error" in result

    def test_empty_document_id(self):
        ctx = _mock_ctx()
        result = create_paragraph_bullets("", 1, 10, ctx=ctx)
        assert "error" in result


class TestDeleteParagraphBullets:
    """Tests for delete_paragraph_bullets."""

    def test_removes_bullets(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = delete_paragraph_bullets("doc1", 1, 50, ctx=ctx)
        assert result["clearedRange"] == {"startIndex": 1, "endIndex": 50}

    def test_invalid_range(self):
        ctx = _mock_ctx()
        result = delete_paragraph_bullets("doc1", 20, 10, ctx=ctx)
        assert "error" in result

    def test_empty_document_id(self):
        ctx = _mock_ctx()
        result = delete_paragraph_bullets("", 1, 10, ctx=ctx)
        assert "error" in result


class TestBatchUpdateDocument:
    """Tests for batch_update_document."""

    def test_sends_multiple_requests(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = {"replies": [{}, {}]}
        ctx = _mock_ctx(docs_service=svc)

        requests = [
            {"insertText": {"location": {"index": 1}, "text": "Hello\n"}},
            {
                "updateParagraphStyle": {
                    "range": {"startIndex": 1, "endIndex": 7},
                    "paragraphStyle": {"namedStyleType": "HEADING_1"},
                    "fields": "namedStyleType",
                }
            },
        ]

        result = batch_update_document("doc1", requests, ctx=ctx)
        assert result["requestCount"] == 2
        assert len(result["replies"]) == 2

    def test_empty_requests_error(self):
        ctx = _mock_ctx()
        result = batch_update_document("doc1", [], ctx=ctx)
        assert "error" in result

    def test_empty_document_id(self):
        ctx = _mock_ctx()
        result = batch_update_document("", [{"insertText": {}}], ctx=ctx)
        assert "error" in result

    def test_invalid_request_not_dict(self):
        ctx = _mock_ctx()
        result = batch_update_document("doc1", ["not a dict"], ctx=ctx)
        assert "error" in result
        assert "index 0" in result["error"]

    def test_empty_dict_request(self):
        ctx = _mock_ctx()
        result = batch_update_document("doc1", [{}], ctx=ctx)
        assert "error" in result
        assert "non-empty dict" in result["error"]

    def test_api_error_propagated(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.side_effect = Exception("API down")
        ctx = _mock_ctx(docs_service=svc)

        result = batch_update_document(
            "doc1", [{"insertText": {"location": {"index": 1}, "text": "Hi"}}], ctx=ctx
        )
        assert "error" in result

    def test_single_request(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = {"replies": [{}]}
        ctx = _mock_ctx(docs_service=svc)

        result = batch_update_document(
            "doc1",
            [{"insertPageBreak": {"location": {"index": 1}}}],
            ctx=ctx,
        )
        assert result["requestCount"] == 1


class TestUpdateDocumentStyle:
    """Tests for update_document_style."""

    def test_sets_margins(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = update_document_style("doc1", margin_top=72, margin_bottom=72, ctx=ctx)
        assert "marginTop" in result["appliedStyles"]
        assert "marginBottom" in result["appliedStyles"]

    def test_sets_page_preset(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = update_document_style("doc1", page_preset="A4", ctx=ctx)
        assert "pageSize" in result["appliedStyles"]

    def test_sets_custom_page_size(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = update_document_style("doc1", page_width=500, page_height=700, ctx=ctx)
        assert "pageSize" in result["appliedStyles"]

    def test_sets_landscape(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = update_document_style("doc1", landscape=True, ctx=ctx)
        assert "flipPageOrientation" in result["appliedStyles"]

    def test_sets_page_number_start(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = update_document_style("doc1", page_number_start=2, ctx=ctx)
        assert "pageNumberStart" in result["appliedStyles"]

    def test_invalid_page_preset(self):
        ctx = _mock_ctx()
        result = update_document_style("doc1", page_preset="TABLOID", ctx=ctx)
        assert "error" in result

    def test_no_styles_error(self):
        ctx = _mock_ctx()
        result = update_document_style("doc1", ctx=ctx)
        assert "error" in result

    def test_empty_document_id(self):
        ctx = _mock_ctx()
        result = update_document_style("", margin_top=72, ctx=ctx)
        assert "error" in result

    def test_negative_margin(self):
        ctx = _mock_ctx()
        result = update_document_style("doc1", margin_top=-1, ctx=ctx)
        assert "error" in result
        assert "margin_top" in result["error"]

    def test_margin_exceeds_max(self):
        ctx = _mock_ctx()
        result = update_document_style("doc1", margin_left=721, ctx=ctx)
        assert "error" in result
        assert "720" in result["error"]

    def test_page_width_zero(self):
        ctx = _mock_ctx()
        result = update_document_style("doc1", page_width=0, ctx=ctx)
        assert "error" in result

    def test_page_width_exceeds_max(self):
        ctx = _mock_ctx()
        result = update_document_style("doc1", page_width=2001, ctx=ctx)
        assert "error" in result
        assert "2000" in result["error"]

    def test_page_height_zero(self):
        ctx = _mock_ctx()
        result = update_document_style("doc1", page_height=0, ctx=ctx)
        assert "error" in result

    def test_page_height_exceeds_max(self):
        ctx = _mock_ctx()
        result = update_document_style("doc1", page_height=2001, ctx=ctx)
        assert "error" in result

    def test_api_error_propagated(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.side_effect = Exception("API down")
        ctx = _mock_ctx(docs_service=svc)

        result = update_document_style("doc1", margin_top=72, ctx=ctx)
        assert "error" in result


class TestInsertSectionBreak:
    """Tests for insert_section_break."""

    def test_next_page_break(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = insert_section_break("doc1", index=10, ctx=ctx)
        assert result["sectionType"] == "NEXT_PAGE"
        assert result["insertedAt"] == 10

    def test_continuous_break(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = insert_section_break(
            "doc1", index=5, section_type="CONTINUOUS", ctx=ctx
        )
        assert result["sectionType"] == "CONTINUOUS"

    def test_invalid_section_type(self):
        ctx = _mock_ctx()
        result = insert_section_break("doc1", section_type="INVALID", ctx=ctx)
        assert "error" in result

    def test_empty_document_id(self):
        ctx = _mock_ctx()
        result = insert_section_break("", ctx=ctx)
        assert "error" in result


class TestInsertInlineImage:
    """Tests for insert_inline_image."""

    def test_inserts_image(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = insert_inline_image(
            "doc1", uri="https://example.com/img.png", index=5, ctx=ctx
        )
        assert result["insertedAt"] == 5
        assert result["uri"] == "https://example.com/img.png"

    def test_inserts_with_dimensions(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = _batch_ok()
        ctx = _mock_ctx(docs_service=svc)

        result = insert_inline_image(
            "doc1",
            uri="https://example.com/img.png",
            width=144,
            height=72,
            ctx=ctx,
        )
        assert result["documentId"] == "doc1"

    def test_empty_uri(self):
        ctx = _mock_ctx()
        result = insert_inline_image("doc1", uri="", ctx=ctx)
        assert "error" in result

    def test_http_uri_rejected(self):
        ctx = _mock_ctx()
        result = insert_inline_image("doc1", uri="http://example.com/img.png", ctx=ctx)
        assert "error" in result
        assert "HTTPS" in result["error"]

    def test_ftp_uri_rejected(self):
        ctx = _mock_ctx()
        result = insert_inline_image("doc1", uri="ftp://example.com/img.png", ctx=ctx)
        assert "error" in result

    def test_negative_width(self):
        ctx = _mock_ctx()
        result = insert_inline_image(
            "doc1", uri="https://example.com/img.png", width=-10, ctx=ctx
        )
        assert "error" in result
        assert "width" in result["error"]

    def test_zero_width(self):
        ctx = _mock_ctx()
        result = insert_inline_image(
            "doc1", uri="https://example.com/img.png", width=0, ctx=ctx
        )
        assert "error" in result

    def test_negative_height(self):
        ctx = _mock_ctx()
        result = insert_inline_image(
            "doc1", uri="https://example.com/img.png", height=-5, ctx=ctx
        )
        assert "error" in result
        assert "height" in result["error"]

    def test_empty_document_id(self):
        ctx = _mock_ctx()
        result = insert_inline_image("", uri="https://example.com/img.png", ctx=ctx)
        assert "error" in result

    def test_api_error_propagated(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.side_effect = Exception("API down")
        ctx = _mock_ctx(docs_service=svc)

        result = insert_inline_image("doc1", uri="https://example.com/img.png", ctx=ctx)
        assert "error" in result


class TestCreateFootnote:
    """Tests for create_footnote."""

    def test_creates_footnote(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = {
            "replies": [{"createFootnote": {"footnoteId": "fn_123"}}]
        }
        ctx = _mock_ctx(docs_service=svc)

        result = create_footnote("doc1", index=10, ctx=ctx)
        assert result["footnoteId"] == "fn_123"
        assert result["insertedAt"] == 10

    def test_default_index(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = {
            "replies": [{"createFootnote": {"footnoteId": "fn_456"}}]
        }
        ctx = _mock_ctx(docs_service=svc)

        result = create_footnote("doc1", ctx=ctx)
        assert result["insertedAt"] == 1

    def test_empty_document_id(self):
        ctx = _mock_ctx()
        result = create_footnote("", ctx=ctx)
        assert "error" in result
