"""Comment operations for Google Docs (via Drive API)."""

from typing import Any, Dict, Optional

from mcp.server.fastmcp import Context

from ...registry import ToolParameter, ToolRegistry
from ._utils import validate_document_id


def add_comment(
    document_id: str,
    content: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Add a comment to a Google Document."""
    if err := validate_document_id(document_id):
        return err
    if not content or not content.strip():
        return {"error": "content must be a non-empty string"}

    drive_service = ctx.request_context.lifespan_context.drive_service

    return (
        drive_service.comments()
        .create(
            fileId=document_id,
            body={"content": content},
            fields="id,content,author,createdTime,modifiedTime,resolved",
        )
        .execute()
    )


def get_comment(
    document_id: str,
    comment_id: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get a specific comment on a Google Document."""
    if err := validate_document_id(document_id):
        return err
    if not comment_id or not comment_id.strip():
        return {"error": "comment_id must be a non-empty string"}

    drive_service = ctx.request_context.lifespan_context.drive_service

    return (
        drive_service.comments()
        .get(
            fileId=document_id,
            commentId=comment_id,
            fields="id,content,author,createdTime,modifiedTime,resolved,replies",
        )
        .execute()
    )


def list_comments(
    document_id: str,
    include_deleted: bool = False,
    max_results: int = 20,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """List all comments on a Google Document."""
    if err := validate_document_id(document_id):
        return err

    drive_service = ctx.request_context.lifespan_context.drive_service
    max_results = min(max(1, max_results), 100)

    result = (
        drive_service.comments()
        .list(
            fileId=document_id,
            fields=(
                "comments(id,content,author,createdTime,"
                "modifiedTime,resolved,replies),nextPageToken"
            ),
            includeDeleted=include_deleted,
            pageSize=max_results,
        )
        .execute()
    )

    return {
        "documentId": document_id,
        "comments": result.get("comments", []),
        "next_page_token": result.get("nextPageToken"),
    }


def reply_to_comment(
    document_id: str,
    comment_id: str,
    content: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Reply to a comment on a Google Document."""
    if err := validate_document_id(document_id):
        return err
    if not comment_id or not comment_id.strip():
        return {"error": "comment_id must be a non-empty string"}
    if not content or not content.strip():
        return {"error": "content must be a non-empty string"}

    drive_service = ctx.request_context.lifespan_context.drive_service

    return (
        drive_service.replies()
        .create(
            fileId=document_id,
            commentId=comment_id,
            body={"content": content},
            fields="id,content,author,createdTime,modifiedTime",
        )
        .execute()
    )


def resolve_comment(
    document_id: str,
    comment_id: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Mark a comment on a Google Document as resolved."""
    if err := validate_document_id(document_id):
        return err
    if not comment_id or not comment_id.strip():
        return {"error": "comment_id must be a non-empty string"}

    drive_service = ctx.request_context.lifespan_context.drive_service

    return (
        drive_service.comments()
        .update(
            fileId=document_id,
            commentId=comment_id,
            body={"resolved": True},
            fields="id,resolved,content,author",
        )
        .execute()
    )


def delete_comment(
    document_id: str,
    comment_id: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Delete a comment from a Google Document."""
    if err := validate_document_id(document_id):
        return err
    if not comment_id or not comment_id.strip():
        return {"error": "comment_id must be a non-empty string"}

    drive_service = ctx.request_context.lifespan_context.drive_service

    drive_service.comments().delete(
        fileId=document_id,
        commentId=comment_id,
    ).execute()

    return {
        "documentId": document_id,
        "commentId": comment_id,
        "deleted": True,
    }


def register(registry: ToolRegistry) -> None:
    """Register all Docs comment tools in the registry."""
    registry.register(
        name="add_comment",
        description="Add a comment to a Google Document.",
        parameters=[
            ToolParameter(
                "document_id", "string", "The ID of the document (from URL)"
            ),
            ToolParameter("content", "string", "Comment text content"),
        ],
        tags=["docs", "comments", "add", "create", "feedback", "annotate"],
        fn=add_comment,
    )

    registry.register(
        name="get_comment",
        description="Get a specific comment on a Google Document by comment ID.",
        parameters=[
            ToolParameter(
                "document_id", "string", "The ID of the document (from URL)"
            ),
            ToolParameter("comment_id", "string", "The comment ID to retrieve"),
        ],
        tags=["docs", "comments", "get", "read", "feedback"],
        fn=get_comment,
        read_only=True,
    )

    registry.register(
        name="list_comments",
        description="List all comments on a Google Document.",
        parameters=[
            ToolParameter(
                "document_id", "string", "The ID of the document (from URL)"
            ),
            ToolParameter(
                "include_deleted",
                "boolean",
                "Include deleted comments (default: false)",
                required=False,
                default=False,
            ),
            ToolParameter(
                "max_results",
                "integer",
                "Max comments to return (default: 20, max: 100)",
                required=False,
                default=20,
            ),
        ],
        tags=["docs", "comments", "list", "read", "feedback", "review"],
        fn=list_comments,
        read_only=True,
    )

    registry.register(
        name="reply_to_comment",
        description="Reply to a comment on a Google Document.",
        parameters=[
            ToolParameter(
                "document_id", "string", "The ID of the document (from URL)"
            ),
            ToolParameter("comment_id", "string", "The comment ID to reply to"),
            ToolParameter("content", "string", "Reply text content"),
        ],
        tags=["docs", "comments", "reply", "write", "feedback", "respond"],
        fn=reply_to_comment,
    )

    registry.register(
        name="resolve_comment",
        description="Mark a comment on a Google Document as resolved.",
        parameters=[
            ToolParameter(
                "document_id", "string", "The ID of the document (from URL)"
            ),
            ToolParameter("comment_id", "string", "The comment ID to resolve"),
        ],
        tags=["docs", "comments", "resolve", "close", "done", "feedback"],
        fn=resolve_comment,
    )

    registry.register(
        name="delete_comment",
        description="Delete a comment from a Google Document.",
        parameters=[
            ToolParameter(
                "document_id", "string", "The ID of the document (from URL)"
            ),
            ToolParameter("comment_id", "string", "The comment ID to delete"),
        ],
        tags=["docs", "comments", "delete", "remove", "feedback"],
        fn=delete_comment,
    )
