"""Tests for Google Sheets formatting operations."""

from unittest.mock import MagicMock

import pytest

from mcp_google_workspace.tools.sheets.format import (
    add_conditional_formatting,
    auto_resize_columns,
    auto_resize_rows,
    copy_formatting,
    delete_chart,
    delete_conditional_formatting,
    format_cells,
    freeze_rows_columns,
    get_conditional_formatting,
    group_columns,
    group_rows,
    protect_range,
    read_cell_format,
    set_column_widths,
    set_dropdown_validation,
    set_row_heights,
    ungroup_columns,
    ungroup_rows,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _mock_ctx(sheets_service=None):
    ctx = MagicMock()
    lifespan = MagicMock()
    lifespan.sheets_service = sheets_service or MagicMock()
    ctx.request_context.lifespan_context = lifespan
    return ctx


def _svc_with_sheet_id(sheet_id=0):
    """Create a sheets service mock that returns a specific sheet ID."""
    svc = MagicMock()
    svc.spreadsheets().get().execute.return_value = {
        "sheets": [{"properties": {"title": "S", "sheetId": sheet_id}}],
    }
    svc.spreadsheets().batchUpdate().execute.return_value = {"replies": []}
    return svc


def _svc_no_sheet():
    """Create a sheets service mock where no sheet matches."""
    svc = MagicMock()
    svc.spreadsheets().get().execute.return_value = {
        "sheets": [{"properties": {"title": "Other", "sheetId": 0}}],
    }
    return svc


# ---------------------------------------------------------------------------
# format_cells
# ---------------------------------------------------------------------------


class TestFormatCells:
    def test_applies_bold(self):
        svc = _svc_with_sheet_id(0)
        result = format_cells("sid", "S", "A1:B2", bold=True, ctx=_mock_ctx(svc))
        assert "replies" in result

    def test_applies_italic(self):
        svc = _svc_with_sheet_id(0)
        result = format_cells("sid", "S", "A1", italic=True, ctx=_mock_ctx(svc))
        assert "replies" in result

    def test_applies_font_size(self):
        svc = _svc_with_sheet_id(0)
        result = format_cells("sid", "S", "A1", font_size=14, ctx=_mock_ctx(svc))
        assert "replies" in result

    def test_applies_font_family(self):
        svc = _svc_with_sheet_id(0)
        result = format_cells("sid", "S", "A1", font_family="Arial", ctx=_mock_ctx(svc))
        assert "replies" in result

    def test_applies_foreground_color(self):
        svc = _svc_with_sheet_id(0)
        result = format_cells(
            "sid", "S", "A1",
            foreground_color={"red": 1.0, "green": 0.0, "blue": 0.0},
            ctx=_mock_ctx(svc),
        )
        assert "replies" in result

    def test_applies_background_color(self):
        svc = _svc_with_sheet_id(0)
        result = format_cells(
            "sid", "S", "A1",
            background_color={"red": 0.0, "green": 1.0, "blue": 0.0},
            ctx=_mock_ctx(svc),
        )
        assert "replies" in result

    def test_applies_number_format(self):
        svc = _svc_with_sheet_id(0)
        result = format_cells(
            "sid", "S", "A1",
            number_format_type="CURRENCY",
            number_format_pattern="#,##0.00",
            ctx=_mock_ctx(svc),
        )
        assert "replies" in result

    def test_applies_multiple_formats(self):
        svc = _svc_with_sheet_id(0)
        result = format_cells(
            "sid", "S", "A1:C3",
            bold=True,
            italic=True,
            font_size=12,
            horizontal_alignment="CENTER",
            ctx=_mock_ctx(svc),
        )
        assert "replies" in result

    def test_sheet_not_found(self):
        result = format_cells("sid", "Missing", "A1", bold=True, ctx=_mock_ctx(_svc_no_sheet()))
        assert "error" in result

    def test_invalid_range(self):
        svc = _svc_with_sheet_id(0)
        result = format_cells("sid", "S", "!!!bad", bold=True, ctx=_mock_ctx(svc))
        assert "error" in result

    def test_no_format_options_returns_error(self):
        svc = _svc_with_sheet_id(0)
        result = format_cells("sid", "S", "A1", ctx=_mock_ctx(svc))
        assert "error" in result
        assert "At least one" in result["error"]

    def test_font_size_too_small(self):
        svc = _svc_with_sheet_id(0)
        result = format_cells("sid", "S", "A1", font_size=0, ctx=_mock_ctx(svc))
        assert "error" in result
        assert "font_size" in result["error"]

    def test_font_size_too_large(self):
        svc = _svc_with_sheet_id(0)
        result = format_cells("sid", "S", "A1", font_size=500, ctx=_mock_ctx(svc))
        assert "error" in result
        assert "font_size" in result["error"]

    def test_invalid_horizontal_alignment(self):
        svc = _svc_with_sheet_id(0)
        result = format_cells("sid", "S", "A1", horizontal_alignment="INVALID", ctx=_mock_ctx(svc))
        assert "error" in result
        assert "horizontal_alignment" in result["error"]

    @pytest.mark.parametrize("alignment", ["LEFT", "CENTER", "RIGHT"])
    def test_valid_horizontal_alignments(self, alignment):
        svc = _svc_with_sheet_id(0)
        result = format_cells("sid", "S", "A1", horizontal_alignment=alignment, ctx=_mock_ctx(svc))
        assert "replies" in result

    def test_invalid_vertical_alignment(self):
        svc = _svc_with_sheet_id(0)
        result = format_cells("sid", "S", "A1", vertical_alignment="INVALID", ctx=_mock_ctx(svc))
        assert "error" in result
        assert "vertical_alignment" in result["error"]

    @pytest.mark.parametrize("alignment", ["TOP", "MIDDLE", "BOTTOM"])
    def test_valid_vertical_alignments(self, alignment):
        svc = _svc_with_sheet_id(0)
        result = format_cells("sid", "S", "A1", vertical_alignment=alignment, ctx=_mock_ctx(svc))
        assert "replies" in result

    def test_invalid_wrap_strategy(self):
        svc = _svc_with_sheet_id(0)
        result = format_cells("sid", "S", "A1", wrap_strategy="INVALID", ctx=_mock_ctx(svc))
        assert "error" in result
        assert "wrap_strategy" in result["error"]

    @pytest.mark.parametrize("strategy", ["OVERFLOW_CELL", "LEGACY_WRAP", "CLIP", "WRAP"])
    def test_valid_wrap_strategies(self, strategy):
        svc = _svc_with_sheet_id(0)
        result = format_cells("sid", "S", "A1", wrap_strategy=strategy, ctx=_mock_ctx(svc))
        assert "replies" in result

    def test_case_insensitive_alignment(self):
        svc = _svc_with_sheet_id(0)
        result = format_cells("sid", "S", "A1", horizontal_alignment="center", ctx=_mock_ctx(svc))
        assert "replies" in result


# ---------------------------------------------------------------------------
# read_cell_format
# ---------------------------------------------------------------------------


class TestReadCellFormat:
    def test_reads_format(self):
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "sheets": [
                {
                    "data": [
                        {
                            "rowData": [
                                {
                                    "values": [
                                        {"userEnteredFormat": {"textFormat": {"bold": True}}}
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        result = read_cell_format("sid", "S", "A1", ctx=_mock_ctx(svc))
        assert result["spreadsheetId"] == "sid"
        assert result["range"] == "S!A1"
        assert len(result["formats"]) == 1
        assert result["formats"][0][0]["textFormat"]["bold"] is True

    def test_empty_result(self):
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {"sheets": []}
        result = read_cell_format("sid", "S", "A1", ctx=_mock_ctx(svc))
        assert result["formats"] == []

    def test_falls_back_to_effective_format(self):
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "sheets": [
                {
                    "data": [
                        {
                            "rowData": [
                                {
                                    "values": [
                                        {"effectiveFormat": {"textFormat": {"italic": True}}}
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        result = read_cell_format("sid", "S", "A1", ctx=_mock_ctx(svc))
        assert result["formats"][0][0]["textFormat"]["italic"] is True


# ---------------------------------------------------------------------------
# freeze_rows_columns
# ---------------------------------------------------------------------------


class TestFreezeRowsColumns:
    def test_freezes(self):
        svc = _svc_with_sheet_id(0)
        result = freeze_rows_columns("sid", "S", frozen_rows=1, frozen_columns=2, ctx=_mock_ctx(svc))
        assert "replies" in result

    def test_unfreeze(self):
        svc = _svc_with_sheet_id(0)
        result = freeze_rows_columns("sid", "S", frozen_rows=0, frozen_columns=0, ctx=_mock_ctx(svc))
        assert "replies" in result

    def test_sheet_not_found(self):
        result = freeze_rows_columns("sid", "Missing", ctx=_mock_ctx(_svc_no_sheet()))
        assert "error" in result


# ---------------------------------------------------------------------------
# set_column_widths
# ---------------------------------------------------------------------------


class TestSetColumnWidths:
    def test_sets_width(self):
        svc = _svc_with_sheet_id(0)
        result = set_column_widths("sid", "S", 0, 3, 200, ctx=_mock_ctx(svc))
        assert "replies" in result

    def test_sheet_not_found(self):
        result = set_column_widths("sid", "Missing", 0, 1, 100, ctx=_mock_ctx(_svc_no_sheet()))
        assert "error" in result

    def test_negative_start_column(self):
        svc = _svc_with_sheet_id(0)
        result = set_column_widths("sid", "S", -1, 1, 100, ctx=_mock_ctx(svc))
        assert "error" in result

    def test_end_not_greater_than_start(self):
        svc = _svc_with_sheet_id(0)
        result = set_column_widths("sid", "S", 5, 5, 100, ctx=_mock_ctx(svc))
        assert "error" in result

    def test_width_zero(self):
        svc = _svc_with_sheet_id(0)
        result = set_column_widths("sid", "S", 0, 1, 0, ctx=_mock_ctx(svc))
        assert "error" in result

    def test_width_exceeds_max(self):
        svc = _svc_with_sheet_id(0)
        result = set_column_widths("sid", "S", 0, 1, 20000, ctx=_mock_ctx(svc))
        assert "error" in result


# ---------------------------------------------------------------------------
# set_row_heights
# ---------------------------------------------------------------------------


class TestSetRowHeights:
    def test_sets_height(self):
        svc = _svc_with_sheet_id(0)
        result = set_row_heights("sid", "S", 0, 5, 40, ctx=_mock_ctx(svc))
        assert "replies" in result

    def test_sheet_not_found(self):
        result = set_row_heights("sid", "Missing", 0, 1, 40, ctx=_mock_ctx(_svc_no_sheet()))
        assert "error" in result

    def test_negative_start_row(self):
        svc = _svc_with_sheet_id(0)
        result = set_row_heights("sid", "S", -1, 1, 40, ctx=_mock_ctx(svc))
        assert "error" in result

    def test_end_not_greater_than_start(self):
        svc = _svc_with_sheet_id(0)
        result = set_row_heights("sid", "S", 5, 3, 40, ctx=_mock_ctx(svc))
        assert "error" in result

    def test_height_zero(self):
        svc = _svc_with_sheet_id(0)
        result = set_row_heights("sid", "S", 0, 1, 0, ctx=_mock_ctx(svc))
        assert "error" in result

    def test_height_exceeds_max(self):
        svc = _svc_with_sheet_id(0)
        result = set_row_heights("sid", "S", 0, 1, 20000, ctx=_mock_ctx(svc))
        assert "error" in result


# ---------------------------------------------------------------------------
# auto_resize_columns / auto_resize_rows
# ---------------------------------------------------------------------------


class TestAutoResize:
    def test_auto_resize_columns(self):
        svc = _svc_with_sheet_id(0)
        result = auto_resize_columns("sid", "S", ctx=_mock_ctx(svc))
        assert "replies" in result

    def test_auto_resize_columns_with_end(self):
        svc = _svc_with_sheet_id(0)
        result = auto_resize_columns("sid", "S", start_column=0, end_column=5, ctx=_mock_ctx(svc))
        assert "replies" in result

    def test_auto_resize_columns_sheet_not_found(self):
        result = auto_resize_columns("sid", "Missing", ctx=_mock_ctx(_svc_no_sheet()))
        assert "error" in result

    def test_auto_resize_rows(self):
        svc = _svc_with_sheet_id(0)
        result = auto_resize_rows("sid", "S", ctx=_mock_ctx(svc))
        assert "replies" in result

    def test_auto_resize_rows_with_end(self):
        svc = _svc_with_sheet_id(0)
        result = auto_resize_rows("sid", "S", start_row=0, end_row=10, ctx=_mock_ctx(svc))
        assert "replies" in result

    def test_auto_resize_rows_sheet_not_found(self):
        result = auto_resize_rows("sid", "Missing", ctx=_mock_ctx(_svc_no_sheet()))
        assert "error" in result


# ---------------------------------------------------------------------------
# set_dropdown_validation
# ---------------------------------------------------------------------------


class TestSetDropdownValidation:
    def test_creates_dropdown(self):
        svc = _svc_with_sheet_id(0)
        result = set_dropdown_validation(
            "sid", "S", "A1:A10", ["Yes", "No", "Maybe"], ctx=_mock_ctx(svc)
        )
        assert "replies" in result

    def test_sheet_not_found(self):
        result = set_dropdown_validation(
            "sid", "Missing", "A1", ["a"], ctx=_mock_ctx(_svc_no_sheet())
        )
        assert "error" in result

    def test_empty_values_returns_error(self):
        svc = _svc_with_sheet_id(0)
        result = set_dropdown_validation("sid", "S", "A1", [], ctx=_mock_ctx(svc))
        assert "error" in result
        assert "non-empty" in result["error"]

    def test_invalid_range(self):
        svc = _svc_with_sheet_id(0)
        result = set_dropdown_validation("sid", "S", "!!!bad", ["a"], ctx=_mock_ctx(svc))
        assert "error" in result

    def test_strict_false(self):
        svc = _svc_with_sheet_id(0)
        result = set_dropdown_validation(
            "sid", "S", "A1", ["a", "b"], strict=False, ctx=_mock_ctx(svc)
        )
        assert "replies" in result


# ---------------------------------------------------------------------------
# protect_range
# ---------------------------------------------------------------------------


class TestProtectRange:
    def test_protect_whole_sheet(self):
        svc = _svc_with_sheet_id(0)
        result = protect_range("sid", "S", ctx=_mock_ctx(svc))
        assert "replies" in result

    def test_protect_with_range(self):
        svc = _svc_with_sheet_id(0)
        result = protect_range("sid", "S", range="A1:B10", ctx=_mock_ctx(svc))
        assert "replies" in result

    def test_protect_warning_only(self):
        svc = _svc_with_sheet_id(0)
        result = protect_range("sid", "S", warning_only=True, ctx=_mock_ctx(svc))
        assert "replies" in result

    def test_protect_with_description(self):
        svc = _svc_with_sheet_id(0)
        result = protect_range(
            "sid", "S", description="Do not edit", ctx=_mock_ctx(svc)
        )
        assert "replies" in result

    def test_sheet_not_found(self):
        result = protect_range("sid", "Missing", ctx=_mock_ctx(_svc_no_sheet()))
        assert "error" in result

    def test_invalid_range(self):
        svc = _svc_with_sheet_id(0)
        result = protect_range("sid", "S", range="!!!bad", ctx=_mock_ctx(svc))
        assert "error" in result


# ---------------------------------------------------------------------------
# add_conditional_formatting
# ---------------------------------------------------------------------------


class TestAddConditionalFormatting:
    def test_adds_rule_with_bold(self):
        svc = _svc_with_sheet_id(0)
        result = add_conditional_formatting(
            "sid", "S", "A1:A10",
            condition_type="NUMBER_GREATER",
            condition_values=["100"],
            format_bold=True,
            ctx=_mock_ctx(svc),
        )
        assert "replies" in result

    def test_adds_rule_with_background_color(self):
        svc = _svc_with_sheet_id(0)
        result = add_conditional_formatting(
            "sid", "S", "A1:A10",
            condition_type="TEXT_CONTAINS",
            condition_values=["error"],
            format_background_color={"red": 1.0, "green": 0.0, "blue": 0.0},
            ctx=_mock_ctx(svc),
        )
        assert "replies" in result

    def test_adds_rule_with_foreground_color(self):
        svc = _svc_with_sheet_id(0)
        result = add_conditional_formatting(
            "sid", "S", "A1:A10",
            condition_type="BLANK",
            format_foreground_color={"red": 0.5, "green": 0.5, "blue": 0.5},
            ctx=_mock_ctx(svc),
        )
        assert "replies" in result

    def test_no_format_options_returns_error(self):
        svc = _svc_with_sheet_id(0)
        result = add_conditional_formatting(
            "sid", "S", "A1:A10",
            condition_type="BLANK",
            ctx=_mock_ctx(svc),
        )
        assert "error" in result
        assert "At least one" in result["error"]

    def test_sheet_not_found(self):
        result = add_conditional_formatting(
            "sid", "Missing", "A1",
            condition_type="BLANK",
            format_bold=True,
            ctx=_mock_ctx(_svc_no_sheet()),
        )
        assert "error" in result

    def test_invalid_range(self):
        svc = _svc_with_sheet_id(0)
        result = add_conditional_formatting(
            "sid", "S", "!!!bad",
            condition_type="BLANK",
            format_bold=True,
            ctx=_mock_ctx(svc),
        )
        assert "error" in result

    def test_condition_without_values(self):
        svc = _svc_with_sheet_id(0)
        result = add_conditional_formatting(
            "sid", "S", "A1:A10",
            condition_type="NOT_BLANK",
            format_italic=True,
            ctx=_mock_ctx(svc),
        )
        assert "replies" in result


# ---------------------------------------------------------------------------
# get_conditional_formatting
# ---------------------------------------------------------------------------


class TestGetConditionalFormatting:
    def test_gets_rules(self):
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "sheets": [
                {
                    "properties": {"sheetId": 0, "title": "S"},
                    "conditionalFormats": [{"ranges": []}],
                }
            ]
        }
        result = get_conditional_formatting("sid", "S", ctx=_mock_ctx(svc))
        assert result["sheet"] == "S"
        assert len(result["conditionalFormats"]) == 1

    def test_no_rules(self):
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "sheets": [
                {
                    "properties": {"sheetId": 0, "title": "S"},
                }
            ]
        }
        result = get_conditional_formatting("sid", "S", ctx=_mock_ctx(svc))
        assert result["conditionalFormats"] == []

    def test_sheet_not_found(self):
        result = get_conditional_formatting("sid", "Missing", ctx=_mock_ctx(_svc_no_sheet()))
        assert "error" in result


# ---------------------------------------------------------------------------
# delete_conditional_formatting
# ---------------------------------------------------------------------------


class TestDeleteConditionalFormatting:
    def test_deletes_rule(self):
        svc = _svc_with_sheet_id(0)
        result = delete_conditional_formatting("sid", "S", 0, ctx=_mock_ctx(svc))
        assert "replies" in result

    def test_negative_index(self):
        svc = _svc_with_sheet_id(0)
        result = delete_conditional_formatting("sid", "S", -1, ctx=_mock_ctx(svc))
        assert "error" in result
        assert "index" in result["error"]

    def test_sheet_not_found(self):
        result = delete_conditional_formatting("sid", "Missing", 0, ctx=_mock_ctx(_svc_no_sheet()))
        assert "error" in result


# ---------------------------------------------------------------------------
# delete_chart
# ---------------------------------------------------------------------------


class TestDeleteChart:
    def test_deletes_chart(self):
        svc = MagicMock()
        svc.spreadsheets().batchUpdate().execute.return_value = {"replies": []}
        result = delete_chart("sid", 42, ctx=_mock_ctx(svc))
        assert "replies" in result


# ---------------------------------------------------------------------------
# copy_formatting
# ---------------------------------------------------------------------------


class TestCopyFormatting:
    def test_copies_format(self):
        svc = _svc_with_sheet_id(0)
        result = copy_formatting(
            "sid", "S", "A1:B2", "S", "C1:D2", ctx=_mock_ctx(svc)
        )
        assert "replies" in result

    def test_source_sheet_not_found(self):
        result = copy_formatting(
            "sid", "Missing", "A1:B2", "S", "C1:D2", ctx=_mock_ctx(_svc_no_sheet())
        )
        assert "error" in result

    def test_destination_sheet_not_found(self):
        # Service finds source "S" but not destination "Missing"
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "sheets": [{"properties": {"title": "S", "sheetId": 0}}],
        }
        svc.spreadsheets().batchUpdate().execute.return_value = {"replies": []}
        result = copy_formatting(
            "sid", "S", "A1:B2", "Missing", "C1:D2", ctx=_mock_ctx(svc)
        )
        assert "error" in result

    def test_invalid_source_range(self):
        svc = _svc_with_sheet_id(0)
        result = copy_formatting(
            "sid", "S", "!!!bad", "S", "C1:D2", ctx=_mock_ctx(svc)
        )
        assert "error" in result


# ---------------------------------------------------------------------------
# group_rows / ungroup_rows
# ---------------------------------------------------------------------------


class TestGroupRows:
    def test_groups_rows(self):
        svc = _svc_with_sheet_id(0)
        result = group_rows("sid", "S", 0, 5, ctx=_mock_ctx(svc))
        assert "replies" in result

    def test_sheet_not_found(self):
        result = group_rows("sid", "Missing", 0, 5, ctx=_mock_ctx(_svc_no_sheet()))
        assert "error" in result

    def test_negative_start(self):
        svc = _svc_with_sheet_id(0)
        result = group_rows("sid", "S", -1, 5, ctx=_mock_ctx(svc))
        assert "error" in result

    def test_end_not_greater_than_start(self):
        svc = _svc_with_sheet_id(0)
        result = group_rows("sid", "S", 5, 3, ctx=_mock_ctx(svc))
        assert "error" in result


class TestUngroupRows:
    def test_ungroups_rows(self):
        svc = _svc_with_sheet_id(0)
        result = ungroup_rows("sid", "S", 0, 5, ctx=_mock_ctx(svc))
        assert "replies" in result

    def test_sheet_not_found(self):
        result = ungroup_rows("sid", "Missing", 0, 5, ctx=_mock_ctx(_svc_no_sheet()))
        assert "error" in result

    def test_negative_start(self):
        svc = _svc_with_sheet_id(0)
        result = ungroup_rows("sid", "S", -1, 5, ctx=_mock_ctx(svc))
        assert "error" in result

    def test_end_not_greater_than_start(self):
        svc = _svc_with_sheet_id(0)
        result = ungroup_rows("sid", "S", 5, 3, ctx=_mock_ctx(svc))
        assert "error" in result


# ---------------------------------------------------------------------------
# group_columns / ungroup_columns
# ---------------------------------------------------------------------------


class TestGroupColumns:
    def test_groups_columns(self):
        svc = _svc_with_sheet_id(0)
        result = group_columns("sid", "S", 0, 3, ctx=_mock_ctx(svc))
        assert "replies" in result

    def test_sheet_not_found(self):
        result = group_columns("sid", "Missing", 0, 3, ctx=_mock_ctx(_svc_no_sheet()))
        assert "error" in result

    def test_negative_start(self):
        svc = _svc_with_sheet_id(0)
        result = group_columns("sid", "S", -1, 3, ctx=_mock_ctx(svc))
        assert "error" in result

    def test_end_not_greater_than_start(self):
        svc = _svc_with_sheet_id(0)
        result = group_columns("sid", "S", 5, 3, ctx=_mock_ctx(svc))
        assert "error" in result


class TestUngroupColumns:
    def test_ungroups_columns(self):
        svc = _svc_with_sheet_id(0)
        result = ungroup_columns("sid", "S", 0, 3, ctx=_mock_ctx(svc))
        assert "replies" in result

    def test_sheet_not_found(self):
        result = ungroup_columns("sid", "Missing", 0, 3, ctx=_mock_ctx(_svc_no_sheet()))
        assert "error" in result

    def test_negative_start(self):
        svc = _svc_with_sheet_id(0)
        result = ungroup_columns("sid", "S", -1, 3, ctx=_mock_ctx(svc))
        assert "error" in result

    def test_end_not_greater_than_start(self):
        svc = _svc_with_sheet_id(0)
        result = ungroup_columns("sid", "S", 5, 3, ctx=_mock_ctx(svc))
        assert "error" in result
