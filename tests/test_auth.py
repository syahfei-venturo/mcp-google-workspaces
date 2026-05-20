"""Tests for authentication and credential security in auth.py."""

import base64
import json
import os
import stat
from unittest.mock import MagicMock, patch

import pytest

from mcp_google_workspace.auth import (
    _MAX_CREDENTIALS_BASE64_BYTES,
    _resolve_credentials,
    _try_adc,
    _try_base64_credentials,
    _try_oauth,
    _try_service_account,
    _write_token,
)


# ---------------------------------------------------------------------------
# _write_token: secure file permissions
# ---------------------------------------------------------------------------


class TestWriteToken:
    """Token files must be created with owner-only permissions (0600)."""

    def test_creates_file_with_0600(self, tmp_path):
        token_path = str(tmp_path / "token.json")
        with patch("mcp_google_workspace.auth.TOKEN_PATH", token_path):
            _write_token('{"access_token": "secret"}')

        mode = stat.S_IMODE(os.stat(token_path).st_mode)
        assert mode == 0o600, f"Expected 0600, got {oct(mode)}"

    def test_overwrites_existing_file_preserving_permissions(self, tmp_path):
        token_path = str(tmp_path / "token.json")
        with patch("mcp_google_workspace.auth.TOKEN_PATH", token_path):
            _write_token('{"v": 1}')
            _write_token('{"v": 2}')

        mode = stat.S_IMODE(os.stat(token_path).st_mode)
        assert mode == 0o600
        with open(token_path) as f:
            assert json.load(f) == {"v": 2}

    def test_creates_parent_directory_with_0700(self, tmp_path):
        nested = tmp_path / "subdir" / "token.json"
        with patch("mcp_google_workspace.auth.TOKEN_PATH", str(nested)):
            _write_token("{}")

        dir_mode = stat.S_IMODE(os.stat(str(nested.parent)).st_mode)
        assert dir_mode == 0o700, f"Expected 0700 on dir, got {oct(dir_mode)}"

    def test_corrects_preexisting_file_with_wrong_permissions(self, tmp_path):
        """If token file already exists with loose permissions, chmod fixes it."""
        token_path = tmp_path / "token.json"
        token_path.write_text('{"old": true}')
        os.chmod(str(token_path), 0o644)  # simulate misconfigured file

        with patch("mcp_google_workspace.auth.TOKEN_PATH", str(token_path)):
            _write_token('{"new": true}')

        mode = stat.S_IMODE(os.stat(str(token_path)).st_mode)
        assert mode == 0o600, f"Expected 0600 after correction, got {oct(mode)}"


# ---------------------------------------------------------------------------
# _try_base64_credentials: size limit and validation
# ---------------------------------------------------------------------------


class TestTryBase64Credentials:
    """Base64 credential decoding must enforce size limits and handle errors."""

    def test_returns_none_when_not_configured(self):
        with patch("mcp_google_workspace.auth.CREDENTIALS_CONFIG", None):
            assert _try_base64_credentials() is None

    def test_rejects_oversized_payload(self):
        oversized = "A" * (_MAX_CREDENTIALS_BASE64_BYTES + 1)
        with patch("mcp_google_workspace.auth.CREDENTIALS_CONFIG", oversized):
            assert _try_base64_credentials() is None

    def test_rejects_invalid_base64(self):
        with patch(
            "mcp_google_workspace.auth.CREDENTIALS_CONFIG", "not-valid-base64!!!"
        ):
            assert _try_base64_credentials() is None

    def test_rejects_corrupt_base64_binascii_error(self):
        """Triggers binascii.Error rather than ValueError."""
        with patch(
            "mcp_google_workspace.auth.CREDENTIALS_CONFIG", "====invalid===="
        ):
            assert _try_base64_credentials() is None

    def test_rejects_invalid_json(self):
        # Valid base64 but not valid JSON
        raw = base64.b64encode(b"this is not json").decode()
        with patch("mcp_google_workspace.auth.CREDENTIALS_CONFIG", raw):
            assert _try_base64_credentials() is None

    def test_accepts_valid_credentials(self):
        fake_sa = {
            "type": "service_account",
            "project_id": "test",
            "private_key_id": "key123",
            "private_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIE...fake\n-----END RSA PRIVATE KEY-----\n",
            "client_email": "test@test.iam.gserviceaccount.com",
            "client_id": "123",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
        encoded = base64.b64encode(json.dumps(fake_sa).encode()).decode()
        with patch("mcp_google_workspace.auth.CREDENTIALS_CONFIG", encoded):
            with patch(
                "mcp_google_workspace.auth.service_account.Credentials"
                ".from_service_account_info"
            ) as mock_sa:
                mock_sa.return_value = MagicMock()
                result = _try_base64_credentials()
                assert result is not None
                mock_sa.assert_called_once()


# ---------------------------------------------------------------------------
# _try_service_account
# ---------------------------------------------------------------------------


class TestTryServiceAccount:

    def test_returns_none_when_path_empty(self):
        with patch("mcp_google_workspace.auth.SERVICE_ACCOUNT_PATH", ""):
            assert _try_service_account() is None

    def test_returns_none_when_file_missing(self, tmp_path):
        with patch(
            "mcp_google_workspace.auth.SERVICE_ACCOUNT_PATH",
            str(tmp_path / "nope.json"),
        ):
            assert _try_service_account() is None

    def test_returns_creds_on_success(self, tmp_path):
        sa_file = tmp_path / "sa.json"
        sa_file.write_text("{}")
        with patch(
            "mcp_google_workspace.auth.SERVICE_ACCOUNT_PATH", str(sa_file)
        ):
            with patch(
                "mcp_google_workspace.auth.service_account.Credentials"
                ".from_service_account_file"
            ) as mock_load:
                mock_load.return_value = MagicMock()
                result = _try_service_account()
                assert result is not None

    def test_returns_none_on_invalid_json(self, tmp_path):
        sa_file = tmp_path / "bad.json"
        sa_file.write_text("not json")
        with patch(
            "mcp_google_workspace.auth.SERVICE_ACCOUNT_PATH", str(sa_file)
        ):
            with patch(
                "mcp_google_workspace.auth.service_account.Credentials"
                ".from_service_account_file",
                side_effect=json.JSONDecodeError("err", "doc", 0),
            ):
                assert _try_service_account() is None


# ---------------------------------------------------------------------------
# _try_oauth
# ---------------------------------------------------------------------------


class TestTryOAuth:

    def test_returns_valid_cached_token(self, tmp_path):
        token_path = tmp_path / "token.json"
        token_path.write_text("{}")
        mock_creds = MagicMock()
        mock_creds.valid = True

        with patch("mcp_google_workspace.auth.TOKEN_PATH", str(token_path)):
            with patch(
                "mcp_google_workspace.auth.Credentials.from_authorized_user_info",
                return_value=mock_creds,
            ):
                result = _try_oauth()
                assert result is mock_creds

    def test_refreshes_expired_token(self, tmp_path):
        token_path = tmp_path / "token.json"
        token_path.write_text("{}")
        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "rt"
        mock_creds.to_json.return_value = '{"refreshed": true}'

        with patch("mcp_google_workspace.auth.TOKEN_PATH", str(token_path)):
            with patch(
                "mcp_google_workspace.auth.Credentials.from_authorized_user_info",
                return_value=mock_creds,
            ):
                result = _try_oauth()
                mock_creds.refresh.assert_called_once()
                assert result is mock_creds

    def test_returns_none_on_refresh_and_flow_failure(self, tmp_path):
        token_path = tmp_path / "token.json"
        token_path.write_text("{}")
        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "rt"
        mock_creds.refresh.side_effect = OSError("refresh failed")

        with patch("mcp_google_workspace.auth.TOKEN_PATH", str(token_path)):
            with patch(
                "mcp_google_workspace.auth.Credentials.from_authorized_user_info",
                return_value=mock_creds,
            ):
                with patch(
                    "mcp_google_workspace.auth.InstalledAppFlow"
                    ".from_client_secrets_file",
                    side_effect=OSError("no secrets"),
                ):
                    result = _try_oauth()
                    assert result is None


# ---------------------------------------------------------------------------
# _try_adc
# ---------------------------------------------------------------------------


class TestTryADC:

    def test_returns_adc_credentials(self):
        mock_creds = MagicMock()
        with patch(
            "mcp_google_workspace.auth.google.auth.default",
            return_value=(mock_creds, "project-id"),
        ):
            result = _try_adc()
            assert result is mock_creds

    def test_raises_on_failure(self):
        with patch(
            "mcp_google_workspace.auth.google.auth.default",
            side_effect=Exception("no creds"),
        ):
            with pytest.raises(Exception, match="no creds"):
                _try_adc()


# ---------------------------------------------------------------------------
# _resolve_credentials
# ---------------------------------------------------------------------------


class TestResolveCredentials:

    def test_uses_first_successful_strategy(self):
        mock_creds = MagicMock()
        with (
            patch(
                "mcp_google_workspace.auth._try_base64_credentials",
                return_value=None,
            ),
            patch(
                "mcp_google_workspace.auth._try_service_account",
                return_value=mock_creds,
            ),
            patch(
                "mcp_google_workspace.auth._try_oauth",
            ) as mock_oauth,
        ):
            result = _resolve_credentials()
            assert result is mock_creds
            mock_oauth.assert_not_called()

    def test_falls_through_to_adc(self):
        mock_creds = MagicMock()
        with (
            patch(
                "mcp_google_workspace.auth._try_base64_credentials",
                return_value=None,
            ),
            patch(
                "mcp_google_workspace.auth._try_service_account",
                return_value=None,
            ),
            patch(
                "mcp_google_workspace.auth._try_oauth",
                return_value=None,
            ),
            patch(
                "mcp_google_workspace.auth._try_adc",
                return_value=mock_creds,
            ),
        ):
            result = _resolve_credentials()
            assert result is mock_creds

    def test_raises_when_all_fail(self):
        with (
            patch(
                "mcp_google_workspace.auth._try_base64_credentials",
                return_value=None,
            ),
            patch(
                "mcp_google_workspace.auth._try_service_account",
                return_value=None,
            ),
            patch(
                "mcp_google_workspace.auth._try_oauth",
                return_value=None,
            ),
            patch(
                "mcp_google_workspace.auth._try_adc",
                side_effect=Exception("ADC failed"),
            ),
        ):
            with pytest.raises(Exception, match="All authentication methods"):
                _resolve_credentials()
