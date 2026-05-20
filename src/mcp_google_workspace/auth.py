"""Authentication and lifecycle management for Google Workspace APIs."""

import asyncio
import base64
import binascii
import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Optional

import google.auth
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from mcp.server.fastmcp import FastMCP

from .context import WorkspaceContext

logger = logging.getLogger(__name__)

# Scopes for all supported Google Workspace services
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
]

CREDENTIALS_CONFIG = os.environ.get("CREDENTIALS_CONFIG")
_DEFAULT_TOKEN_DIR = os.path.join(
    os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
    "mcp-google-workspace",
)
TOKEN_PATH = os.environ.get(
    "TOKEN_PATH",
    os.path.join(_DEFAULT_TOKEN_DIR, "token.json"),
)
CREDENTIALS_PATH = os.environ.get("CREDENTIALS_PATH", "credentials.json")
SERVICE_ACCOUNT_PATH = os.environ.get("SERVICE_ACCOUNT_PATH", "service_account.json")
DRIVE_FOLDER_ID = os.environ.get("DRIVE_FOLDER_ID", "")


def _ensure_token_dir() -> None:
    """Create the token directory with restricted permissions if needed."""
    token_dir = os.path.dirname(TOKEN_PATH)
    if token_dir:
        os.makedirs(token_dir, mode=0o700, exist_ok=True)


def _write_token(content: str) -> None:
    """Write token data to disk with owner-only permissions (0600)."""
    _ensure_token_dir()
    fd = os.open(TOKEN_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as token_file:
        token_file.write(content)
    # Ensure mode even if file pre-existed with wrong permissions.
    os.chmod(TOKEN_PATH, 0o600)


# Maximum size (bytes) for base64-encoded credentials to prevent DoS via
# memory exhaustion.  A typical service-account JSON is ~2 KB; 1 MB is
# generous headroom for any reasonable credential payload.
_MAX_CREDENTIALS_BASE64_BYTES = 1_000_000


def _validate_credential_path(path: str, label: str) -> bool:
    """Check that *path* exists, is a regular file, and not a symlink.

    Returns ``True`` when the path is safe to use.  Logs a warning and
    returns ``False`` otherwise.
    """
    if not path or not os.path.exists(path):
        return False
    if os.path.islink(path):
        logger.warning(
            "%s path '%s' is a symlink — refusing to follow for security",
            label,
            path,
        )
        return False
    if not os.path.isfile(path):
        logger.warning(
            "%s path '%s' is not a regular file",
            label,
            path,
        )
        return False
    return True


def _try_base64_credentials() -> Optional[Any]:
    """Attempt auth via base64-encoded credentials config."""
    if not CREDENTIALS_CONFIG:
        return None

    if len(CREDENTIALS_CONFIG) > _MAX_CREDENTIALS_BASE64_BYTES:
        logger.error(
            "CREDENTIALS_CONFIG exceeds %d bytes (%d), refusing to decode",
            _MAX_CREDENTIALS_BASE64_BYTES,
            len(CREDENTIALS_CONFIG),
        )
        return None

    try:
        decoded = base64.b64decode(CREDENTIALS_CONFIG)
        info = json.loads(decoded)
    except (ValueError, json.JSONDecodeError, binascii.Error) as exc:
        logger.error("Invalid CREDENTIALS_CONFIG: %s", exc)
        return None

    return service_account.Credentials.from_service_account_info(
        info, scopes=SCOPES
    )


def _try_service_account() -> Optional[Any]:
    """Attempt auth via service account JSON file."""
    if not _validate_credential_path(SERVICE_ACCOUNT_PATH, "SERVICE_ACCOUNT_PATH"):
        return None
    try:
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_PATH, scopes=SCOPES
        )
        logger.info("Using service account authentication")
        logger.info(
            "Working with Google Drive folder ID: %s",
            DRIVE_FOLDER_ID or "Not specified",
        )
        return creds
    except (FileNotFoundError, json.JSONDecodeError, ValueError, KeyError) as e:
        logger.error("Error using service account authentication: %s", e)
        return None


def _try_oauth() -> Optional[Any]:
    """Attempt auth via OAuth 2.0 flow (interactive)."""
    logger.info("Trying OAuth authentication flow")
    creds = None

    if _validate_credential_path(TOKEN_PATH, "TOKEN_PATH"):
        with open(TOKEN_PATH, "r") as token:
            creds = Credentials.from_authorized_user_info(json.load(token), SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            logger.info("Attempting to refresh expired token...")
            creds.refresh(Request())
            logger.info("Token refreshed successfully")
            _write_token(creds.to_json())
            return creds
        except (google.auth.exceptions.RefreshError, google.auth.exceptions.TransportError, OSError) as refresh_error:
            logger.warning("Token refresh failed: %s", refresh_error)
            creds = None

    if not _validate_credential_path(CREDENTIALS_PATH, "CREDENTIALS_PATH"):
        return None

    try:
        flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
        creds = flow.run_local_server(port=8085)
        _write_token(creds.to_json())
        logger.info("Successfully authenticated using OAuth flow")
        return creds
    except (FileNotFoundError, ValueError, KeyError, OSError) as e:
        logger.error("Error with OAuth flow: %s", e)
        return None


def _try_adc() -> Any:
    """Attempt auth via Application Default Credentials. Raises on failure."""
    logger.info("Attempting to use Application Default Credentials (ADC)")
    creds, project = google.auth.default(scopes=SCOPES)
    logger.info("Successfully authenticated using ADC for project: %s", project)
    return creds


def _resolve_credentials() -> Any:
    """Try each auth method in priority order, return first success."""
    for strategy in [_try_base64_credentials, _try_service_account, _try_oauth]:
        creds = strategy()
        if creds is not None:
            return creds

    try:
        return _try_adc()
    except Exception as e:
        logger.error("Error using Application Default Credentials: %s", e)
        raise Exception(
            "All authentication methods failed. Please configure credentials."
        )


def _build_services(creds: Any) -> WorkspaceContext:
    """Build all Google API service clients (blocking I/O)."""
    return WorkspaceContext(
        sheets_service=build("sheets", "v4", credentials=creds),
        docs_service=build("docs", "v1", credentials=creds),
        drive_service=build("drive", "v3", credentials=creds),
        folder_id=DRIVE_FOLDER_ID if DRIVE_FOLDER_ID else None,
    )


@asynccontextmanager
async def workspace_lifespan(
    server: FastMCP,
) -> AsyncIterator[WorkspaceContext]:
    """Manage Google Workspace API connection lifecycle.

    Credential resolution and client building are blocking I/O — offloaded
    to a thread so the event loop is not stalled during startup.
    """
    loop = asyncio.get_running_loop()
    creds = await loop.run_in_executor(None, _resolve_credentials)
    ctx = await loop.run_in_executor(None, _build_services, creds)
    yield ctx
