"""Tests for retry_on_api_error decorator."""

from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError

from mcp_google_workspace.utils.common import retry_on_api_error


def _make_http_error(status: int) -> HttpError:
    """Create a mock HttpError with a given status code."""
    resp = MagicMock()
    resp.status = status
    return HttpError(resp=resp, content=b"error")


def _mock_fn(side_effect):
    """Create a MagicMock with __name__ set (required by @wraps / logger)."""
    fn = MagicMock(side_effect=side_effect)
    fn.__name__ = "mock_api_call"
    fn.__wrapped__ = None
    return fn


class TestRetryOnApiError:
    """Tests for the retry_on_api_error decorator."""

    def test_success_on_first_try(self):
        fn = _mock_fn(side_effect=["ok"])
        wrapped = retry_on_api_error(fn)
        assert wrapped() == "ok"
        assert fn.call_count == 1

    def test_retries_on_429(self):
        fn = _mock_fn(side_effect=[_make_http_error(429), "ok"])
        wrapped = retry_on_api_error(fn)
        with patch("mcp_google_workspace.utils.common.time.sleep"):
            assert wrapped() == "ok"
        assert fn.call_count == 2

    def test_retries_on_500(self):
        fn = _mock_fn(side_effect=[_make_http_error(500), "ok"])
        wrapped = retry_on_api_error(fn)
        with patch("mcp_google_workspace.utils.common.time.sleep"):
            assert wrapped() == "ok"
        assert fn.call_count == 2

    def test_retries_on_503(self):
        fn = _mock_fn(side_effect=[_make_http_error(503), "ok"])
        wrapped = retry_on_api_error(fn)
        with patch("mcp_google_workspace.utils.common.time.sleep"):
            assert wrapped() == "ok"
        assert fn.call_count == 2

    def test_no_retry_on_400(self):
        fn = _mock_fn(side_effect=_make_http_error(400))
        wrapped = retry_on_api_error(fn)
        with pytest.raises(HttpError):
            wrapped()
        assert fn.call_count == 1

    def test_no_retry_on_403(self):
        fn = _mock_fn(side_effect=_make_http_error(403))
        wrapped = retry_on_api_error(fn)
        with pytest.raises(HttpError):
            wrapped()
        assert fn.call_count == 1

    def test_no_retry_on_404(self):
        fn = _mock_fn(side_effect=_make_http_error(404))
        wrapped = retry_on_api_error(fn)
        with pytest.raises(HttpError):
            wrapped()
        assert fn.call_count == 1

    def test_raises_after_max_retries(self):
        fn = _mock_fn(
            side_effect=[_make_http_error(429)] * 4  # 1 initial + 3 retries
        )
        wrapped = retry_on_api_error(fn)
        with patch("mcp_google_workspace.utils.common.time.sleep"):
            with pytest.raises(HttpError):
                wrapped()
        assert fn.call_count == 4  # 1 + 3 retries

    def test_exponential_backoff_delays(self):
        fn = _mock_fn(
            side_effect=[_make_http_error(500), _make_http_error(500), "ok"]
        )
        wrapped = retry_on_api_error(fn)
        with patch("mcp_google_workspace.utils.common.time.sleep") as mock_sleep:
            wrapped()
        # First retry: 1.0 * 2^0 = 1.0, second retry: 1.0 * 2^1 = 2.0
        assert mock_sleep.call_count == 2
        assert mock_sleep.call_args_list[0][0][0] == 1.0
        assert mock_sleep.call_args_list[1][0][0] == 2.0

    def test_preserves_function_name(self):
        def my_api_call():
            pass

        wrapped = retry_on_api_error(my_api_call)
        assert wrapped.__name__ == "my_api_call"

    def test_passes_args_and_kwargs(self):
        fn = _mock_fn(side_effect=["ok"])
        wrapped = retry_on_api_error(fn)
        wrapped("a", "b", key="val")
        fn.assert_called_once_with("a", "b", key="val")

    def test_success_after_two_transient_failures(self):
        fn = _mock_fn(
            side_effect=[
                _make_http_error(503),
                _make_http_error(429),
                "recovered",
            ]
        )
        wrapped = retry_on_api_error(fn)
        with patch("mcp_google_workspace.utils.common.time.sleep"):
            assert wrapped() == "recovered"
        assert fn.call_count == 3
