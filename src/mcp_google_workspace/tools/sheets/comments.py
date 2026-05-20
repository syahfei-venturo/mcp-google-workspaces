"""Comment operations for Google Sheets (via Drive API)."""

from typing import Any, Dict, Optional

from mcp.server.fastmcp import Context

from ...registry import ToolParameter, ToolRegistry


def list_sheets_comments(
    spreadsheet_id: str,
    include_deleted: bool = False,
    max_results: int = 20,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """List comments on a Google Spreadsheet."""
    drive_service = ctx.request_context.lifespan_context.drive_service
    max_results = min(max(1, max_results), 100)

    result = (
        drive_service.comments()
        .list(
            fileId=spreadsheet_id,
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
        "spreadsheetId": spreadsheet_id,
        "comments": result.get("comments", []),
        "next_page_token": result.get("nextPageToken"),
    }


def get_sheets_comment(
    spreadsheet_id: str,
    comment_id: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get a specific comment on a Google Spreadsheet."""
    if not comment_id or not comment_id.strip():
        return {"error": "comment_id must be a non-empty string"}

    drive_service = ctx.request_context.lifespan_context.drive_service

    return (
        drive_service.comments()
        .get(
            fileId=spreadsheet_id,
            commentId=comment_id,
            fields="id,content,author,createdTime,modifiedTime,resolved,replies",
        )
        .execute()
    )


def reply_to_sheets_comment(
    spreadsheet_id: str,
    comment_id: str,
    content: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Reply to a comment on a Google Spreadsheet."""
    if not comment_id or not comment_id.strip():
        return {"error": "comment_id must be a non-empty string"}
    if not content or not content.strip():
        return {"error": "content must be a non-empty string"}

    drive_service = ctx.request_context.lifespan_context.drive_service

    return (
        drive_service.replies()
        .create(
            fileId=spreadsheet_id,
            commentId=comment_id,
            body={"content": content},
            fields="id,content,author,createdTime,modifiedTime",
        )
        .execute()
    )


def resolve_sheets_comment(
    spreadsheet_id: str,
    comment_id: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Mark a comment on a Google Spreadsheet as resolved."""
    if not comment_id or not comment_id.strip():
        return {"error": "comment_id must be a non-empty string"}

    drive_service = ctx.request_context.lifespan_context.drive_service

    return (
        drive_service.comments()
        .update(
            fileId=spreadsheet_id,
            commentId=comment_id,
            body={"resolved": True},
            fields="id,resolved,content,author",
        )
        .execute()
    )


def delete_sheets_comment(
    spreadsheet_id: str,
    comment_id: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Delete a comment from a Google Spreadsheet."""
    if not comment_id or not comment_id.strip():
        return {"error": "comment_id must be a non-empty string"}

    drive_service = ctx.request_context.lifespan_context.drive_service

    drive_service.comments().delete(
        fileId=spreadsheet_id,
        commentId=comment_id,
    ).execute()

    return {
        "spreadsheetId": spreadsheet_id,
        "commentId": comment_id,
        "deleted": True,
    }


def register(registry: ToolRegistry) -> None:
    """Register all Sheets comment tools in the registry."""
    registry.register(
        name="list_sheets_comments",
        description="List comments on a Google Spreadsheet.",
        parameters=[
            ToolParameter(
                "spreadsheet_id", "string", "The ID of the spreadsheet (from URL)"
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
        tags=["sheets", "comments", "list", "read", "feedback", "review"],
        fn=list_sheets_comments,
        read_only=True,
    )

    registry.register(
        name="get_sheets_comment",
        description="Get a specific comment on a Google Spreadsheet by comment ID.",
        parameters=[
            ToolParameter(
                "spreadsheet_id", "string", "The ID of the spreadsheet (from URL)"
            ),
            ToolParameter("comment_id", "string", "The comment ID to retrieve"),
        ],
        tags=["sheets", "comments", "get", "read", "feedback"],
        fn=get_sheets_comment,
        read_only=True,
    )

    registry.register(
        name="reply_to_sheets_comment",
        description="Reply to a comment on a Google Spreadsheet.",
        parameters=[
            ToolParameter(
                "spreadsheet_id", "string", "The ID of the spreadsheet (from URL)"
            ),
            ToolParameter("comment_id", "string", "The comment ID to reply to"),
            ToolParameter("content", "string", "Reply text content"),
        ],
        tags=["sheets", "comments", "reply", "write", "feedback", "respond"],
        fn=reply_to_sheets_comment,
    )

    registry.register(
        name="resolve_sheets_comment",
        description="Mark a comment on a Google Spreadsheet as resolved.",
        parameters=[
            ToolParameter(
                "spreadsheet_id", "string", "The ID of the spreadsheet (from URL)"
            ),
            ToolParameter("comment_id", "string", "The comment ID to resolve"),
        ],
        tags=["sheets", "comments", "resolve", "close", "done", "feedback"],
        fn=resolve_sheets_comment,
    )

    registry.register(
        name="delete_sheets_comment",
        description="Delete a comment from a Google Spreadsheet.",
        parameters=[
            ToolParameter(
                "spreadsheet_id", "string", "The ID of the spreadsheet (from URL)"
            ),
            ToolParameter("comment_id", "string", "The comment ID to delete"),
        ],
        tags=["sheets", "comments", "delete", "remove", "feedback"],
        fn=delete_sheets_comment,
    )
