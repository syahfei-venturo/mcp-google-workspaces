"""Utility functions specific to Google Sheets operations."""

import logging
import re
from typing import Any, Dict, Optional

from .common import validate_google_id

logger = logging.getLogger(__name__)


def validate_spreadsheet_id(
    spreadsheet_id: str,
) -> Optional[Dict[str, str]]:
    """Return error dict if spreadsheet_id is invalid, else None."""
    return validate_google_id(spreadsheet_id, "spreadsheet_id")


class SheetNotFoundError(ValueError):
    """Raised when a sheet name cannot be resolved to a numeric sheet ID."""


def column_index_to_letter(index: int) -> str:
    """Convert 0-based column index to A1 notation letter (0='A', 25='Z', 26='AA')."""
    result = ""
    while index >= 0:
        result = chr(index % 26 + ord("A")) + result
        index = index // 26 - 1
    return result


def letter_to_column_index(letter: str) -> int:
    """Convert A1 notation letter to 0-based column index ('A'=0, 'Z'=25, 'AA'=26)."""
    result = 0
    for char in letter.upper():
        result = result * 26 + (ord(char) - ord("A") + 1)
    return result - 1


def parse_a1_notation(range_str: str) -> Dict[str, int]:
    """Parse A1 notation range to row/column indices.

    Returns dict with applicable keys: startRowIndex, endRowIndex,
    startColumnIndex, endColumnIndex. Not all keys present for all formats.
    """
    match = re.match(r"^([A-Z]+)?(\d+)?(?::([A-Z]+)?(\d+)?)?$", range_str.upper())
    if not match:
        raise ValueError(f"Invalid A1 notation: {range_str}")

    start_col, start_row, end_col, end_row = match.groups()
    result: Dict[str, int] = {}

    if start_col:
        result["startColumnIndex"] = letter_to_column_index(start_col)
    if start_row:
        result["startRowIndex"] = int(start_row) - 1
    if end_col:
        result["endColumnIndex"] = letter_to_column_index(end_col) + 1
    elif start_col:
        result["endColumnIndex"] = result["startColumnIndex"] + 1
    if end_row:
        result["endRowIndex"] = int(end_row)
    elif start_row:
        result["endRowIndex"] = result["startRowIndex"] + 1

    return result


def get_sheet_id_or_error(
    sheets_service: Any, spreadsheet_id: str, sheet_name: str
) -> int:
    """Return the numeric sheet ID or raise :class:`SheetNotFoundError`.

    Raises
    ------
    SheetNotFoundError
        If *sheet_name* does not exist in the spreadsheet.
    """
    sheet_id = get_sheet_id(sheets_service, spreadsheet_id, sheet_name)
    if sheet_id is None:
        raise SheetNotFoundError(
            f"Sheet '{sheet_name}' not found in spreadsheet {spreadsheet_id}"
        )
    return sheet_id


def get_sheet_id(
    sheets_service: Any, spreadsheet_id: str, sheet_name: str
) -> Optional[int]:
    """Get the numeric sheet ID for a given sheet name."""
    try:
        spreadsheet = (
            sheets_service.spreadsheets()
            .get(
                spreadsheetId=spreadsheet_id,
                fields="sheets(properties(title,sheetId))",
            )
            .execute()
        )
        for sheet in spreadsheet.get("sheets", []):
            if sheet["properties"]["title"] == sheet_name:
                return sheet["properties"]["sheetId"]
        return None
    except Exception as e:
        logger.error(
            "Error looking up sheet '%s' in spreadsheet %s: %s",
            sheet_name,
            spreadsheet_id,
            e,
        )
        return None
