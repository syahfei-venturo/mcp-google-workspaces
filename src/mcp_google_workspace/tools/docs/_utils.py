"""Shared utilities for Google Docs tool modules."""

import json
import logging
import re
import time
from typing import Any, Dict, Optional

from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

# Retry configuration for rate-limit (HTTP 429) and transient errors
_RETRYABLE_STATUS_CODES = frozenset({429, 500, 503})
_MAX_RETRIES = 5
_BASE_DELAY = 2.0  # seconds; doubles each attempt → 2, 4, 8, 16, 32


def validate_document_id(document_id: str) -> Optional[Dict[str, str]]:
    """Return error dict if document_id is invalid, else None.

    Google document IDs are alphanumeric with hyphens/underscores, typically 44 chars.
    """
    from ...utils.common import validate_google_id

    return validate_google_id(document_id, "document_id")


def pt(magnitude: float) -> Dict[str, Any]:
    """Build a Dimension in PT units."""
    return {"magnitude": magnitude, "unit": "PT"}


def validate_uri(uri: str) -> Optional[Dict[str, str]]:
    """Validate URI for image insertion. Must be non-empty HTTPS URL."""
    if not uri or not uri.strip():
        return {"error": "uri must be a non-empty string"}
    if not re.match(r"^https://", uri, re.IGNORECASE):
        return {"error": "uri must use HTTPS scheme (https://)"}
    return None


def safe_batch_update(docs_service, document_id: str, requests: list) -> Dict[str, Any]:
    """Execute batchUpdate with error handling and retry on rate-limit.

    Retries up to ``_MAX_RETRIES`` times with exponential backoff for
    HTTP 429/500/503.  Returns the raw API response on success, or a
    dict with an ``error`` key on failure.
    """
    for attempt in range(_MAX_RETRIES + 1):
        try:
            return (
                docs_service.documents()
                .batchUpdate(documentId=document_id, body={"requests": requests})
                .execute()
            )
        except HttpError as e:
            status = e.resp.status if hasattr(e, "resp") else 0
            if status in _RETRYABLE_STATUS_CODES and attempt < _MAX_RETRIES:
                delay = _BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "Batch update rate-limited (HTTP %d), retrying in %.1fs "
                    "(attempt %d/%d)",
                    status,
                    delay,
                    attempt + 1,
                    _MAX_RETRIES,
                )
                time.sleep(delay)
                continue
            try:
                error_content = json.loads(e.content)
                msg = error_content.get("error", {}).get("message", str(e))
            except (json.JSONDecodeError, AttributeError):
                msg = str(e)
            return {"error": f"Google API error: {msg}"}
        except Exception as e:
            return {"error": f"Failed to update document: {e}"}
    # Unreachable, but satisfies type checker
    return {"error": "Max retries exceeded"}


def safe_get_document(docs_service, document_id: str) -> Dict[str, Any]:
    """Read a document with retry on transient/rate-limit errors.

    Returns the raw document dict on success, or a dict with an
    ``error`` key on failure.
    """
    for attempt in range(_MAX_RETRIES + 1):
        try:
            return (
                docs_service.documents()
                .get(documentId=document_id)
                .execute()
            )
        except HttpError as e:
            status = e.resp.status if hasattr(e, "resp") else 0
            if status in _RETRYABLE_STATUS_CODES and attempt < _MAX_RETRIES:
                delay = _BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "Document read rate-limited (HTTP %d), retrying in %.1fs "
                    "(attempt %d/%d)",
                    status,
                    delay,
                    attempt + 1,
                    _MAX_RETRIES,
                )
                time.sleep(delay)
                continue
            logger.error(
                "Google API error reading document %s: %s", document_id, e
            )
            return {"error": f"Google API error reading document: {e}"}
        except Exception as e:
            logger.error(
                "Failed to read document %s: %s", document_id, e, exc_info=True
            )
            return {"error": f"Failed to read document: {e}"}
    return {"error": "Max retries exceeded"}
