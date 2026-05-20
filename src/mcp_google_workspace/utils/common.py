"""Shared utility functions for all Google Workspace services."""

import logging
import time
from functools import wraps
from typing import Any, Callable, Dict, Optional, Tuple, TypeVar

from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def validate_required_string(
    value: Optional[str], field_name: str
) -> Optional[Dict[str, str]]:
    """Return an error dict if *value* is empty/blank, else ``None``."""
    if not value or not value.strip():
        return {"error": f"{field_name} must be a non-empty string"}
    return None


# ---------------------------------------------------------------------------
# Drive query helpers
# ---------------------------------------------------------------------------


def escape_drive_value(value: str) -> str:
    """Escape a value for safe interpolation into a Drive API query string."""
    return value.replace("\\", "\\\\").replace("'", "\\'")

F = TypeVar("F", bound=Callable[..., Any])

_RETRYABLE_STATUS_CODES = {429, 500, 503}
_MAX_RETRIES = 3
_BASE_DELAY = 1.0


def retry_on_api_error(fn: F) -> F:
    """Decorator that retries Google API calls on transient/rate-limit errors.

    Retries up to 3 times with exponential backoff for HTTP 429, 500, 503.
    """

    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        last_error: Optional[Exception] = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                return fn(*args, **kwargs)
            except HttpError as e:
                last_error = e
                if e.resp.status not in _RETRYABLE_STATUS_CODES:
                    raise
                if attempt == _MAX_RETRIES:
                    raise
                delay = _BASE_DELAY * (2**attempt)
                logger.warning(
                    "API call %s failed (HTTP %d), retrying in %.1fs (attempt %d/%d)",
                    fn.__name__,
                    e.resp.status,
                    delay,
                    attempt + 1,
                    _MAX_RETRIES,
                )
                time.sleep(delay)
        raise last_error  # unreachable, but satisfies type checker

    return wrapper  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Drive create helper
# ---------------------------------------------------------------------------


def drive_create_with_fallback(
    drive_service: Any,
    file_body: Dict[str, Any],
    media_body: Any = None,
    fields: str = "id, name, parents",
) -> Tuple[Dict[str, Any], Optional[str]]:
    """Create a Drive file, falling back to My Drive root if the parent folder is not found.

    Returns ``(result, warning)`` where ``warning`` is a non-empty string when
    the configured folder was invalid and the file was created in root instead.

    Raises ``HttpError`` for any non-404 or non-folder-related API errors.
    """
    warning: Optional[str] = None

    def _do_create(body: Dict[str, Any]) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {
            "supportsAllDrives": True,
            "body": body,
            "fields": fields,
        }
        if media_body is not None:
            kwargs["media_body"] = media_body
        return drive_service.files().create(**kwargs).execute()

    try:
        return _do_create(file_body), warning
    except HttpError as e:
        if e.resp.status == 404 and file_body.get("parents"):
            bad_folder = file_body["parents"][0]
            warning = (
                f"Folder '{bad_folder}' not found — file created in My Drive root. "
                f"Update DRIVE_FOLDER_ID to a valid folder ID."
            )
            fallback_body = {k: v for k, v in file_body.items() if k != "parents"}
            return _do_create(fallback_body), warning
        raise
