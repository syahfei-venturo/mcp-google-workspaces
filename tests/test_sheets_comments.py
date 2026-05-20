"""Tests for Google Sheets comment operations."""

from unittest.mock import MagicMock

import pytest

from mcp_google_workspace.tools.sheets.comments import (
    delete_sheets_comment,
    get_sheets_comment,
    list_sheets_comments,
    reply_to_sheets_comment,
    resolve_sheets_comment,
)


def _mock_ctx(drive_service=None):
    """Create a mock context with drive_service."""
    ctx = MagicMock()
    lifespan = MagicMock()
    if drive_service is None:
        drive_service = MagicMock()
    lifespan.drive_service = drive_service
    ctx.request_context.lifespan_context = lifespan
    return ctx


class TestListSheetsComments:
    """Tests for list_sheets_comments function."""

    def test_happy_path(self):
        """Test successfully listing comments on a spreadsheet."""
        drive_service = MagicMock()
        mock_response = {
            "comments": [
                {
                    "id": "comment1",
                    "content": "Cell needs verification",
                    "resolved": False,
                },
                {
                    "id": "comment2",
                    "content": "Formula is correct",
                    "resolved": True,
                },
            ],
            "nextPageToken": "token456",
        }
        drive_service.comments().list().execute.return_value = mock_response
        ctx = _mock_ctx(drive_service)

        result = list_sheets_comments("sheet123", ctx=ctx)

        assert result["spreadsheetId"] == "sheet123"
        assert len(result["comments"]) == 2
        assert result["next_page_token"] == "token456"
        # Verify the API was called with correct parameters
        list_call = drive_service.comments().list
        assert list_call.call_count >= 1
        call_args = list_call.call_args
        assert call_args.kwargs["fileId"] == "sheet123"
        assert call_args.kwargs["pageSize"] == 20

    def test_with_include_deleted(self):
        """Test listing comments with include_deleted=True."""
        drive_service = MagicMock()
        drive_service.comments().list().execute.return_value = {
            "comments": []
        }
        ctx = _mock_ctx(drive_service)

        list_sheets_comments("sheet123", include_deleted=True, ctx=ctx)

        call_args = drive_service.comments().list.call_args
        assert call_args.kwargs["includeDeleted"] is True

    def test_max_results_clamping_low(self):
        """Test max_results clamped to minimum of 1."""
        drive_service = MagicMock()
        drive_service.comments().list().execute.return_value = {
            "comments": []
        }
        ctx = _mock_ctx(drive_service)

        list_sheets_comments("sheet123", max_results=-5, ctx=ctx)

        call_args = drive_service.comments().list.call_args
        assert call_args.kwargs["pageSize"] == 1

    def test_max_results_clamping_high(self):
        """Test max_results clamped to maximum of 100."""
        drive_service = MagicMock()
        drive_service.comments().list().execute.return_value = {
            "comments": []
        }
        ctx = _mock_ctx(drive_service)

        list_sheets_comments("sheet123", max_results=250, ctx=ctx)

        call_args = drive_service.comments().list.call_args
        assert call_args.kwargs["pageSize"] == 100

    def test_no_next_page_token(self):
        """Test when there is no next page token."""
        drive_service = MagicMock()
        drive_service.comments().list().execute.return_value = {
            "comments": [{"id": "c1", "content": "test"}]
        }
        ctx = _mock_ctx(drive_service)

        result = list_sheets_comments("sheet123", ctx=ctx)

        assert result["next_page_token"] is None

    def test_empty_comments_list(self):
        """Test with no comments on spreadsheet."""
        drive_service = MagicMock()
        drive_service.comments().list().execute.return_value = {
            "comments": []
        }
        ctx = _mock_ctx(drive_service)

        result = list_sheets_comments("sheet123", ctx=ctx)

        assert result["comments"] == []
        assert result["spreadsheetId"] == "sheet123"


class TestGetSheetsComment:
    """Tests for get_sheets_comment function."""

    def test_happy_path(self):
        """Test successfully retrieving a specific comment."""
        drive_service = MagicMock()
        mock_response = {
            "id": "comment123",
            "content": "Please verify this formula",
            "author": {"displayName": "Alice Smith"},
            "createdTime": "2024-01-01T10:00:00Z",
            "modifiedTime": "2024-01-01T10:00:00Z",
            "resolved": False,
            "replies": [],
        }
        drive_service.comments().get().execute.return_value = mock_response
        ctx = _mock_ctx(drive_service)

        result = get_sheets_comment("sheet123", "comment123", ctx)

        assert result == mock_response
        # Verify the API was called with correct parameters
        get_call = drive_service.comments().get
        assert get_call.call_count >= 1
        call_args = get_call.call_args
        assert call_args.kwargs["fileId"] == "sheet123"
        assert call_args.kwargs["commentId"] == "comment123"

    def test_empty_comment_id(self):
        """Test with empty comment_id returns error."""
        ctx = _mock_ctx()
        result = get_sheets_comment("sheet123", "", ctx)

        assert isinstance(result, dict)
        assert "error" in result
        assert "comment_id" in result["error"]

    def test_whitespace_comment_id(self):
        """Test with whitespace-only comment_id returns error."""
        ctx = _mock_ctx()
        result = get_sheets_comment("sheet123", "   ", ctx)

        assert isinstance(result, dict)
        assert "error" in result
        assert "comment_id" in result["error"]

    def test_with_replies(self):
        """Test retrieving comment with replies."""
        drive_service = MagicMock()
        mock_response = {
            "id": "comment123",
            "content": "Question about data",
            "author": {"displayName": "Alice Smith"},
            "resolved": False,
            "replies": [
                {
                    "id": "reply1",
                    "content": "The data is from Q4",
                    "author": {"displayName": "Bob Johnson"},
                },
                {
                    "id": "reply2",
                    "content": "Thanks for clarifying",
                    "author": {"displayName": "Alice Smith"},
                },
            ],
        }
        drive_service.comments().get().execute.return_value = mock_response
        ctx = _mock_ctx(drive_service)

        result = get_sheets_comment("sheet123", "comment123", ctx)

        assert len(result["replies"]) == 2


class TestReplyToSheetsComment:
    """Tests for reply_to_sheets_comment function."""

    def test_happy_path(self):
        """Test successfully replying to a comment on a spreadsheet."""
        drive_service = MagicMock()
        mock_response = {
            "id": "reply456",
            "content": "Looks good to me",
            "author": {"displayName": "Bob Johnson"},
            "createdTime": "2024-01-01T11:00:00Z",
            "modifiedTime": "2024-01-01T11:00:00Z",
        }
        drive_service.replies().create().execute.return_value = mock_response
        ctx = _mock_ctx(drive_service)

        result = reply_to_sheets_comment("sheet123", "comment123", "Looks good to me", ctx)

        assert result == mock_response
        # Verify the API was called with correct parameters
        create_call = drive_service.replies().create
        assert create_call.call_count >= 1
        call_args = create_call.call_args
        assert call_args.kwargs["fileId"] == "sheet123"
        assert call_args.kwargs["commentId"] == "comment123"
        assert call_args.kwargs["body"]["content"] == "Looks good to me"

    def test_empty_comment_id(self):
        """Test with empty comment_id returns error."""
        ctx = _mock_ctx()
        result = reply_to_sheets_comment("sheet123", "", "reply content", ctx)

        assert isinstance(result, dict)
        assert "error" in result
        assert "comment_id" in result["error"]

    def test_empty_content(self):
        """Test with empty content returns error."""
        ctx = _mock_ctx()
        result = reply_to_sheets_comment("sheet123", "comment123", "", ctx)

        assert isinstance(result, dict)
        assert "error" in result
        assert "content" in result["error"]

    def test_whitespace_comment_id(self):
        """Test with whitespace-only comment_id returns error."""
        ctx = _mock_ctx()
        result = reply_to_sheets_comment("sheet123", "   ", "reply content", ctx)

        assert isinstance(result, dict)
        assert "error" in result
        assert "comment_id" in result["error"]

    def test_whitespace_content(self):
        """Test with whitespace-only content returns error."""
        ctx = _mock_ctx()
        result = reply_to_sheets_comment("sheet123", "comment123", "   ", ctx)

        assert isinstance(result, dict)
        assert "error" in result
        assert "content" in result["error"]


class TestResolveSheetsComment:
    """Tests for resolve_sheets_comment function."""

    def test_happy_path(self):
        """Test successfully resolving a comment on a spreadsheet."""
        drive_service = MagicMock()
        mock_response = {
            "id": "comment123",
            "resolved": True,
            "content": "Please verify this formula",
            "author": {"displayName": "Alice Smith"},
        }
        drive_service.comments().update().execute.return_value = mock_response
        ctx = _mock_ctx(drive_service)

        result = resolve_sheets_comment("sheet123", "comment123", ctx)

        assert result == mock_response
        assert result["resolved"] is True
        # Verify the API was called with correct parameters
        update_call = drive_service.comments().update
        assert update_call.call_count >= 1
        call_args = update_call.call_args
        assert call_args.kwargs["fileId"] == "sheet123"
        assert call_args.kwargs["commentId"] == "comment123"
        assert call_args.kwargs["body"]["resolved"] is True

    def test_empty_comment_id(self):
        """Test with empty comment_id returns error."""
        ctx = _mock_ctx()
        result = resolve_sheets_comment("sheet123", "", ctx)

        assert isinstance(result, dict)
        assert "error" in result
        assert "comment_id" in result["error"]

    def test_whitespace_comment_id(self):
        """Test with whitespace-only comment_id returns error."""
        ctx = _mock_ctx()
        result = resolve_sheets_comment("sheet123", "   ", ctx)

        assert isinstance(result, dict)
        assert "error" in result
        assert "comment_id" in result["error"]


class TestDeleteSheetsComment:
    """Tests for delete_sheets_comment function."""

    def test_happy_path(self):
        """Test successfully deleting a comment from a spreadsheet."""
        drive_service = MagicMock()
        drive_service.comments().delete().execute.return_value = None
        ctx = _mock_ctx(drive_service)

        result = delete_sheets_comment("sheet123", "comment123", ctx)

        assert result["deleted"] is True
        assert result["spreadsheetId"] == "sheet123"
        assert result["commentId"] == "comment123"
        # Verify the API was called with correct parameters
        delete_call = drive_service.comments().delete
        assert delete_call.call_count >= 1
        call_args = delete_call.call_args
        assert call_args.kwargs["fileId"] == "sheet123"
        assert call_args.kwargs["commentId"] == "comment123"

    def test_empty_comment_id(self):
        """Test with empty comment_id returns error."""
        ctx = _mock_ctx()
        result = delete_sheets_comment("sheet123", "", ctx)

        assert isinstance(result, dict)
        assert "error" in result
        assert "comment_id" in result["error"]

    def test_whitespace_comment_id(self):
        """Test with whitespace-only comment_id returns error."""
        ctx = _mock_ctx()
        result = delete_sheets_comment("sheet123", "   ", ctx)

        assert isinstance(result, dict)
        assert "error" in result
        assert "comment_id" in result["error"]
