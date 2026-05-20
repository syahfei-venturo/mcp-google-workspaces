"""Tests for Google Docs comment operations."""

from unittest.mock import MagicMock

import pytest

from mcp_google_workspace.tools.docs.comments import (
    add_comment,
    delete_comment,
    get_comment,
    list_comments,
    reply_to_comment,
    resolve_comment,
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


class TestAddComment:
    """Tests for add_comment function."""

    def test_happy_path(self):
        """Test successfully adding a comment."""
        drive_service = MagicMock()
        mock_response = {
            "id": "comment123",
            "content": "Great document!",
            "author": {"displayName": "John Doe"},
            "createdTime": "2024-01-01T10:00:00Z",
            "modifiedTime": "2024-01-01T10:00:00Z",
            "resolved": False,
        }
        drive_service.comments().create().execute.return_value = mock_response
        ctx = _mock_ctx(drive_service)

        result = add_comment("doc123", "Great document!", ctx)

        assert result == mock_response
        # Verify the API was called with correct parameters
        create_call = drive_service.comments().create
        assert create_call.call_count >= 1
        call_args = create_call.call_args
        assert call_args.kwargs["fileId"] == "doc123"
        assert call_args.kwargs["body"]["content"] == "Great document!"

    def test_empty_document_id(self):
        """Test with empty document_id returns error."""
        ctx = _mock_ctx()
        result = add_comment("", "Some content", ctx)

        assert isinstance(result, dict)
        assert "error" in result
        assert "document_id" in result["error"]

    def test_whitespace_document_id(self):
        """Test with whitespace-only document_id returns error."""
        ctx = _mock_ctx()
        result = add_comment("   ", "Some content", ctx)

        assert isinstance(result, dict)
        assert "error" in result
        assert "document_id" in result["error"]

    def test_empty_content(self):
        """Test with empty content returns error."""
        ctx = _mock_ctx()
        result = add_comment("doc123", "", ctx)

        assert isinstance(result, dict)
        assert "error" in result
        assert "content" in result["error"]

    def test_whitespace_content(self):
        """Test with whitespace-only content returns error."""
        ctx = _mock_ctx()
        result = add_comment("doc123", "   ", ctx)

        assert isinstance(result, dict)
        assert "error" in result
        assert "content" in result["error"]


class TestGetComment:
    """Tests for get_comment function."""

    def test_happy_path(self):
        """Test successfully retrieving a comment."""
        drive_service = MagicMock()
        mock_response = {
            "id": "comment123",
            "content": "My feedback",
            "author": {"displayName": "Jane Doe"},
            "createdTime": "2024-01-01T10:00:00Z",
            "modifiedTime": "2024-01-01T10:00:00Z",
            "resolved": False,
            "replies": [],
        }
        drive_service.comments().get().execute.return_value = mock_response
        ctx = _mock_ctx(drive_service)

        result = get_comment("doc123", "comment123", ctx)

        assert result == mock_response
        # Verify the API was called with correct parameters
        get_call = drive_service.comments().get
        assert get_call.call_count >= 1
        call_args = get_call.call_args
        assert call_args.kwargs["fileId"] == "doc123"
        assert call_args.kwargs["commentId"] == "comment123"

    def test_empty_document_id(self):
        """Test with empty document_id returns error."""
        ctx = _mock_ctx()
        result = get_comment("", "comment123", ctx)

        assert isinstance(result, dict)
        assert "error" in result
        assert "document_id" in result["error"]

    def test_empty_comment_id(self):
        """Test with empty comment_id returns error."""
        ctx = _mock_ctx()
        result = get_comment("doc123", "", ctx)

        assert isinstance(result, dict)
        assert "error" in result
        assert "comment_id" in result["error"]

    def test_whitespace_comment_id(self):
        """Test with whitespace-only comment_id returns error."""
        ctx = _mock_ctx()
        result = get_comment("doc123", "   ", ctx)

        assert isinstance(result, dict)
        assert "error" in result
        assert "comment_id" in result["error"]


class TestListComments:
    """Tests for list_comments function."""

    def test_happy_path(self):
        """Test successfully listing comments."""
        drive_service = MagicMock()
        mock_response = {
            "comments": [
                {
                    "id": "comment1",
                    "content": "First comment",
                    "resolved": False,
                },
                {
                    "id": "comment2",
                    "content": "Second comment",
                    "resolved": True,
                },
            ],
            "nextPageToken": "token123",
        }
        drive_service.comments().list().execute.return_value = mock_response
        ctx = _mock_ctx(drive_service)

        result = list_comments("doc123", ctx=ctx)

        assert result["documentId"] == "doc123"
        assert len(result["comments"]) == 2
        assert result["next_page_token"] == "token123"
        # Verify the API was called with correct parameters
        list_call = drive_service.comments().list
        assert list_call.call_count >= 1
        call_args = list_call.call_args
        assert call_args.kwargs["fileId"] == "doc123"
        assert call_args.kwargs["pageSize"] == 20

    def test_empty_document_id(self):
        """Test with empty document_id returns error."""
        ctx = _mock_ctx()
        result = list_comments("", ctx=ctx)

        assert isinstance(result, dict)
        assert "error" in result
        assert "document_id" in result["error"]

    def test_include_deleted(self):
        """Test with include_deleted=True."""
        drive_service = MagicMock()
        drive_service.comments().list().execute.return_value = {
            "comments": []
        }
        ctx = _mock_ctx(drive_service)

        list_comments("doc123", include_deleted=True, ctx=ctx)

        call_args = drive_service.comments().list.call_args
        assert call_args.kwargs["includeDeleted"] is True

    def test_max_results_clamping_low(self):
        """Test max_results clamped to minimum of 1."""
        drive_service = MagicMock()
        drive_service.comments().list().execute.return_value = {
            "comments": []
        }
        ctx = _mock_ctx(drive_service)

        list_comments("doc123", max_results=0, ctx=ctx)

        call_args = drive_service.comments().list.call_args
        assert call_args.kwargs["pageSize"] == 1

    def test_max_results_clamping_high(self):
        """Test max_results clamped to maximum of 100."""
        drive_service = MagicMock()
        drive_service.comments().list().execute.return_value = {
            "comments": []
        }
        ctx = _mock_ctx(drive_service)

        list_comments("doc123", max_results=500, ctx=ctx)

        call_args = drive_service.comments().list.call_args
        assert call_args.kwargs["pageSize"] == 100

    def test_no_next_page_token(self):
        """Test when there is no next page token."""
        drive_service = MagicMock()
        drive_service.comments().list().execute.return_value = {
            "comments": []
        }
        ctx = _mock_ctx(drive_service)

        result = list_comments("doc123", ctx=ctx)

        assert result["next_page_token"] is None


class TestReplyToComment:
    """Tests for reply_to_comment function."""

    def test_happy_path(self):
        """Test successfully replying to a comment."""
        drive_service = MagicMock()
        mock_response = {
            "id": "reply123",
            "content": "Great point!",
            "author": {"displayName": "John Doe"},
            "createdTime": "2024-01-01T11:00:00Z",
            "modifiedTime": "2024-01-01T11:00:00Z",
        }
        drive_service.replies().create().execute.return_value = mock_response
        ctx = _mock_ctx(drive_service)

        result = reply_to_comment("doc123", "comment123", "Great point!", ctx)

        assert result == mock_response
        # Verify the API was called with correct parameters
        create_call = drive_service.replies().create
        assert create_call.call_count >= 1
        call_args = create_call.call_args
        assert call_args.kwargs["fileId"] == "doc123"
        assert call_args.kwargs["commentId"] == "comment123"
        assert call_args.kwargs["body"]["content"] == "Great point!"

    def test_empty_document_id(self):
        """Test with empty document_id returns error."""
        ctx = _mock_ctx()
        result = reply_to_comment("", "comment123", "reply content", ctx)

        assert isinstance(result, dict)
        assert "error" in result
        assert "document_id" in result["error"]

    def test_empty_comment_id(self):
        """Test with empty comment_id returns error."""
        ctx = _mock_ctx()
        result = reply_to_comment("doc123", "", "reply content", ctx)

        assert isinstance(result, dict)
        assert "error" in result
        assert "comment_id" in result["error"]

    def test_empty_content(self):
        """Test with empty content returns error."""
        ctx = _mock_ctx()
        result = reply_to_comment("doc123", "comment123", "", ctx)

        assert isinstance(result, dict)
        assert "error" in result
        assert "content" in result["error"]

    def test_whitespace_content(self):
        """Test with whitespace-only content returns error."""
        ctx = _mock_ctx()
        result = reply_to_comment("doc123", "comment123", "   ", ctx)

        assert isinstance(result, dict)
        assert "error" in result
        assert "content" in result["error"]


class TestResolveComment:
    """Tests for resolve_comment function."""

    def test_happy_path(self):
        """Test successfully resolving a comment."""
        drive_service = MagicMock()
        mock_response = {
            "id": "comment123",
            "resolved": True,
            "content": "My feedback",
            "author": {"displayName": "Jane Doe"},
        }
        drive_service.comments().update().execute.return_value = mock_response
        ctx = _mock_ctx(drive_service)

        result = resolve_comment("doc123", "comment123", ctx)

        assert result == mock_response
        # Verify the API was called with correct parameters
        update_call = drive_service.comments().update
        assert update_call.call_count >= 1
        call_args = update_call.call_args
        assert call_args.kwargs["fileId"] == "doc123"
        assert call_args.kwargs["commentId"] == "comment123"
        assert call_args.kwargs["body"]["resolved"] is True

    def test_empty_document_id(self):
        """Test with empty document_id returns error."""
        ctx = _mock_ctx()
        result = resolve_comment("", "comment123", ctx)

        assert isinstance(result, dict)
        assert "error" in result
        assert "document_id" in result["error"]

    def test_empty_comment_id(self):
        """Test with empty comment_id returns error."""
        ctx = _mock_ctx()
        result = resolve_comment("doc123", "", ctx)

        assert isinstance(result, dict)
        assert "error" in result
        assert "comment_id" in result["error"]

    def test_whitespace_comment_id(self):
        """Test with whitespace-only comment_id returns error."""
        ctx = _mock_ctx()
        result = resolve_comment("doc123", "   ", ctx)

        assert isinstance(result, dict)
        assert "error" in result
        assert "comment_id" in result["error"]


class TestDeleteComment:
    """Tests for delete_comment function."""

    def test_happy_path(self):
        """Test successfully deleting a comment."""
        drive_service = MagicMock()
        drive_service.comments().delete().execute.return_value = None
        ctx = _mock_ctx(drive_service)

        result = delete_comment("doc123", "comment123", ctx)

        assert result["deleted"] is True
        assert result["documentId"] == "doc123"
        assert result["commentId"] == "comment123"
        # Verify the API was called with correct parameters
        delete_call = drive_service.comments().delete
        assert delete_call.call_count >= 1
        call_args = delete_call.call_args
        assert call_args.kwargs["fileId"] == "doc123"
        assert call_args.kwargs["commentId"] == "comment123"

    def test_empty_document_id(self):
        """Test with empty document_id returns error."""
        ctx = _mock_ctx()
        result = delete_comment("", "comment123", ctx)

        assert isinstance(result, dict)
        assert "error" in result
        assert "document_id" in result["error"]

    def test_empty_comment_id(self):
        """Test with empty comment_id returns error."""
        ctx = _mock_ctx()
        result = delete_comment("doc123", "", ctx)

        assert isinstance(result, dict)
        assert "error" in result
        assert "comment_id" in result["error"]

    def test_whitespace_comment_id(self):
        """Test with whitespace-only comment_id returns error."""
        ctx = _mock_ctx()
        result = delete_comment("doc123", "   ", ctx)

        assert isinstance(result, dict)
        assert "error" in result
        assert "comment_id" in result["error"]
