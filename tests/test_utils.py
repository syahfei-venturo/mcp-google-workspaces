"""Tests for utility functions."""

from unittest.mock import MagicMock

import pytest

from mcp_google_workspace.utils import (
    column_index_to_letter,
    escape_drive_value,
    get_sheet_id_or_error,
    letter_to_column_index,
    parse_a1_notation,
    validate_required_string,
)


class TestColumnIndexToLetter:
    """Tests for column_index_to_letter."""

    def test_single_letter_start(self):
        assert column_index_to_letter(0) == "A"

    def test_single_letter_end(self):
        assert column_index_to_letter(25) == "Z"

    def test_double_letter_start(self):
        assert column_index_to_letter(26) == "AA"

    def test_double_letter_mid(self):
        assert column_index_to_letter(27) == "AB"

    def test_double_letter_az(self):
        assert column_index_to_letter(51) == "AZ"

    def test_double_letter_ba(self):
        assert column_index_to_letter(52) == "BA"


class TestLetterToColumnIndex:
    """Tests for letter_to_column_index."""

    def test_single_letter_a(self):
        assert letter_to_column_index("A") == 0

    def test_single_letter_z(self):
        assert letter_to_column_index("Z") == 25

    def test_double_letter_aa(self):
        assert letter_to_column_index("AA") == 26

    def test_double_letter_ab(self):
        assert letter_to_column_index("AB") == 27

    def test_lowercase(self):
        assert letter_to_column_index("a") == 0

    def test_roundtrip(self):
        """column_index_to_letter and letter_to_column_index are inverses."""
        for i in range(100):
            assert letter_to_column_index(column_index_to_letter(i)) == i


class TestParseA1Notation:
    """Tests for parse_a1_notation."""

    def test_single_cell(self):
        result = parse_a1_notation("A1")
        assert result == {
            "startColumnIndex": 0,
            "endColumnIndex": 1,
            "startRowIndex": 0,
            "endRowIndex": 1,
        }

    def test_range(self):
        result = parse_a1_notation("A1:C3")
        assert result == {
            "startColumnIndex": 0,
            "endColumnIndex": 3,
            "startRowIndex": 0,
            "endRowIndex": 3,
        }

    def test_column_only(self):
        result = parse_a1_notation("B:D")
        assert result == {
            "startColumnIndex": 1,
            "endColumnIndex": 4,
        }

    def test_row_only(self):
        result = parse_a1_notation("2:5")
        assert result == {
            "startRowIndex": 1,
            "endRowIndex": 5,
        }

    def test_single_column(self):
        result = parse_a1_notation("C")
        assert result == {
            "startColumnIndex": 2,
            "endColumnIndex": 3,
        }

    def test_case_insensitive(self):
        result = parse_a1_notation("a1:c3")
        assert result == {
            "startColumnIndex": 0,
            "endColumnIndex": 3,
            "startRowIndex": 0,
            "endRowIndex": 3,
        }

    def test_invalid_notation_raises(self):
        with pytest.raises(ValueError, match="Invalid A1 notation"):
            parse_a1_notation("!!!invalid")


# ---------------------------------------------------------------------------
# validate_required_string
# ---------------------------------------------------------------------------


class TestValidateRequiredString:
    """Tests for validate_required_string."""

    def test_valid_string(self):
        assert validate_required_string("hello", "name") is None

    def test_empty_string(self):
        err = validate_required_string("", "title")
        assert err is not None
        assert "title" in err["error"]

    def test_whitespace_only(self):
        err = validate_required_string("   ", "field")
        assert err is not None
        assert "field" in err["error"]

    def test_none_value(self):
        err = validate_required_string(None, "doc_id")
        assert err is not None
        assert "doc_id" in err["error"]


# ---------------------------------------------------------------------------
# escape_drive_value
# ---------------------------------------------------------------------------


class TestEscapeDriveValue:
    """Tests for escape_drive_value."""

    def test_no_special_chars(self):
        assert escape_drive_value("abc123") == "abc123"

    def test_single_quote(self):
        assert escape_drive_value("it's") == "it\\'s"

    def test_backslash(self):
        assert escape_drive_value("a\\b") == "a\\\\b"

    def test_both(self):
        assert escape_drive_value("a\\'b") == "a\\\\\\'b"


# ---------------------------------------------------------------------------
# get_sheet_id_or_error
# ---------------------------------------------------------------------------


class TestGetSheetIdOrError:
    """Tests for get_sheet_id_or_error."""

    def test_returns_id_when_found(self):
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "sheets": [{"properties": {"title": "Sheet1", "sheetId": 42}}]
        }
        result = get_sheet_id_or_error(svc, "sid", "Sheet1")
        assert result == 42

    def test_raises_when_not_found(self):
        svc = MagicMock()
        svc.spreadsheets().get().execute.return_value = {
            "sheets": [{"properties": {"title": "Other", "sheetId": 1}}]
        }
        from mcp_google_workspace.utils.sheets import SheetNotFoundError

        try:
            get_sheet_id_or_error(svc, "sid", "Missing")
            assert False, "Expected SheetNotFoundError"
        except SheetNotFoundError as e:
            assert "Missing" in str(e)
