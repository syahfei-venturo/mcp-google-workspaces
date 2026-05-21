"""Spreadsheet and sheet management operations."""

import json
from typing import Any, Dict, List, Optional

from googleapiclient.errors import HttpError
from mcp.server.fastmcp import Context

from ...registry import ToolParameter, ToolRegistry
from ...utils.common import (
    drive_create_with_fallback,
    escape_drive_value,
    sanitize_http_error,
)
from ...utils.sheets import get_sheet_id, validate_spreadsheet_id


def create_spreadsheet(
    title: str,
    folder_id: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Create a new Google Spreadsheet."""
    if not title or not title.strip():
        return {"error": "title must be a non-empty string"}

    drive_service = ctx.request_context.lifespan_context.drive_service
    target_folder_id = folder_id or ctx.request_context.lifespan_context.folder_id

    file_body: Dict[str, Any] = {
        "name": title,
        "mimeType": "application/vnd.google-apps.spreadsheet",
    }
    if target_folder_id:
        file_body["parents"] = [target_folder_id]

    try:
        spreadsheet, warning = drive_create_with_fallback(drive_service, file_body)
    except HttpError as e:
        return {"error": sanitize_http_error(e, "Create spreadsheet")}

    parents = spreadsheet.get("parents")
    result: Dict[str, Any] = {
        "spreadsheetId": spreadsheet.get("id"),
        "title": spreadsheet.get("name", title),
        "folder": parents[0] if parents else "root",
    }
    if warning:
        result["warning"] = warning
    return result


def create_sheet(
    spreadsheet_id: str,
    title: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Create a new sheet tab in an existing spreadsheet."""
    if err := validate_spreadsheet_id(spreadsheet_id):
        return err
    sheets_service = ctx.request_context.lifespan_context.sheets_service

    result = (
        sheets_service.spreadsheets()
        .batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": title}}}]},
        )
        .execute()
    )

    new_sheet_props = result["replies"][0]["addSheet"]["properties"]
    return {
        "sheetId": new_sheet_props["sheetId"],
        "title": new_sheet_props["title"],
        "index": new_sheet_props.get("index"),
        "spreadsheetId": spreadsheet_id,
    }


def delete_sheet(
    spreadsheet_id: str,
    sheet: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Delete a sheet/tab from a spreadsheet."""
    if err := validate_spreadsheet_id(spreadsheet_id):
        return err
    sheets_service = ctx.request_context.lifespan_context.sheets_service
    sheet_id = get_sheet_id(sheets_service, spreadsheet_id, sheet)

    if sheet_id is None:
        return {"error": f"Sheet '{sheet}' not found"}

    return (
        sheets_service.spreadsheets()
        .batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"deleteSheet": {"sheetId": sheet_id}}]},
        )
        .execute()
    )


def duplicate_spreadsheet(
    spreadsheet_id: str,
    new_title: Optional[str] = None,
    folder_id: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Duplicate an entire spreadsheet."""
    if err := validate_spreadsheet_id(spreadsheet_id):
        return err
    drive_service = ctx.request_context.lifespan_context.drive_service

    body: Dict[str, Any] = {}
    if new_title:
        body["name"] = new_title
    if folder_id:
        body["parents"] = [folder_id]

    result = (
        drive_service.files()
        .copy(
            fileId=spreadsheet_id,
            supportsAllDrives=True,
            body=body,
            fields="id, name, parents",
        )
        .execute()
    )

    parents = result.get("parents")
    return {
        "spreadsheetId": result.get("id"),
        "title": result.get("name"),
        "folder": parents[0] if parents else "root",
    }


def move_spreadsheet(
    spreadsheet_id: str,
    destination_folder_id: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Move a spreadsheet to a different Drive folder."""
    if err := validate_spreadsheet_id(spreadsheet_id):
        return err
    drive_service = ctx.request_context.lifespan_context.drive_service

    current = (
        drive_service.files()
        .get(
            fileId=spreadsheet_id,
            fields="parents",
            supportsAllDrives=True,
        )
        .execute()
    )
    previous_parents = ",".join(current.get("parents", []))

    result = (
        drive_service.files()
        .update(
            fileId=spreadsheet_id,
            addParents=destination_folder_id,
            removeParents=previous_parents,
            supportsAllDrives=True,
            fields="id, name, parents",
        )
        .execute()
    )

    parents = result.get("parents")
    return {
        "spreadsheetId": result.get("id"),
        "title": result.get("name"),
        "folder": parents[0] if parents else "root",
    }


def list_spreadsheets(
    folder_id: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """List spreadsheets in the configured Drive folder."""
    drive_service = ctx.request_context.lifespan_context.drive_service
    target_folder_id = folder_id or ctx.request_context.lifespan_context.folder_id

    warning: Optional[str] = None
    query = "mimeType='application/vnd.google-apps.spreadsheet'"
    if target_folder_id:
        query += f" and '{escape_drive_value(target_folder_id)}' in parents"

    def _list(q: str) -> Dict[str, Any]:
        return (
            drive_service.files()
            .list(
                q=q,
                spaces="drive",
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
                fields="files(id, name)",
                orderBy="modifiedTime desc",
            )
            .execute()
        )

    try:
        results = _list(query)
    except HttpError as e:
        if e.resp.status == 404 and target_folder_id:
            warning = (
                f"Folder '{target_folder_id}' not found — listing My Drive root instead. "
                f"Update DRIVE_FOLDER_ID to a valid folder ID."
            )
            results = _list("mimeType='application/vnd.google-apps.spreadsheet'")
        else:
            return {"error": sanitize_http_error(e, "List spreadsheets"), "items": []}

    items = [{"id": s["id"], "title": s["name"]} for s in results.get("files", [])]
    result: Dict[str, Any] = {"items": items}
    if warning:
        result["warning"] = warning
    return result


def list_sheets(
    spreadsheet_id: str,
    ctx: Optional[Context] = None,
) -> List[str]:
    """List all sheet tab names within a spreadsheet."""
    if err := validate_spreadsheet_id(spreadsheet_id):
        return err
    sheets_service = ctx.request_context.lifespan_context.sheets_service
    spreadsheet = (
        sheets_service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    )
    return [s["properties"]["title"] for s in spreadsheet["sheets"]]


def list_folders(
    parent_folder_id: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> List[Dict[str, str]]:
    """List folders in Google Drive."""
    drive_service = ctx.request_context.lifespan_context.drive_service

    query = "mimeType='application/vnd.google-apps.folder'"
    if parent_folder_id:
        query += f" and '{escape_drive_value(parent_folder_id)}' in parents"
    else:
        query += " and 'root' in parents"

    results = (
        drive_service.files()
        .list(
            q=query,
            spaces="drive",
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
            fields="files(id, name, parents)",
            orderBy="name",
        )
        .execute()
    )

    return [
        {
            "id": f["id"],
            "name": f["name"],
            "parent": (f.get("parents", ["root"])[0] if f.get("parents") else "root"),
        }
        for f in results.get("files", [])
    ]


def copy_sheet(
    src_spreadsheet: str,
    src_sheet: str,
    dst_spreadsheet: str,
    dst_sheet: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Copy a sheet from one spreadsheet to another."""
    if err := validate_spreadsheet_id(src_spreadsheet):
        return err
    if err := validate_spreadsheet_id(dst_spreadsheet):
        return err
    sheets_service = ctx.request_context.lifespan_context.sheets_service
    src_sheet_id = get_sheet_id(sheets_service, src_spreadsheet, src_sheet)

    if src_sheet_id is None:
        return {"error": f"Source sheet '{src_sheet}' not found"}

    copy_result = (
        sheets_service.spreadsheets()
        .sheets()
        .copyTo(
            spreadsheetId=src_spreadsheet,
            sheetId=src_sheet_id,
            body={"destinationSpreadsheetId": dst_spreadsheet},
        )
        .execute()
    )

    if "title" in copy_result and copy_result["title"] != dst_sheet:
        copy_sheet_id = copy_result["sheetId"]
        rename_result = (
            sheets_service.spreadsheets()
            .batchUpdate(
                spreadsheetId=dst_spreadsheet,
                body={
                    "requests": [
                        {
                            "updateSheetProperties": {
                                "properties": {
                                    "sheetId": copy_sheet_id,
                                    "title": dst_sheet,
                                },
                                "fields": "title",
                            }
                        }
                    ]
                },
            )
            .execute()
        )
        return {"copy": copy_result, "rename": rename_result}

    return {"copy": copy_result}


def rename_sheet(
    spreadsheet: str,
    sheet: str,
    new_name: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Rename a sheet tab in a spreadsheet."""
    if err := validate_spreadsheet_id(spreadsheet):
        return err
    sheets_service = ctx.request_context.lifespan_context.sheets_service
    sheet_id = get_sheet_id(sheets_service, spreadsheet, sheet)

    if sheet_id is None:
        return {"error": f"Sheet '{sheet}' not found"}

    return (
        sheets_service.spreadsheets()
        .batchUpdate(
            spreadsheetId=spreadsheet,
            body={
                "requests": [
                    {
                        "updateSheetProperties": {
                            "properties": {
                                "sheetId": sheet_id,
                                "title": new_name,
                            },
                            "fields": "title",
                        }
                    }
                ]
            },
        )
        .execute()
    )


def share_spreadsheet(
    spreadsheet_id: str,
    recipients: List[Dict[str, str]],
    send_notification: bool = True,
    ctx: Optional[Context] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Share a spreadsheet with users via email."""
    if err := validate_spreadsheet_id(spreadsheet_id):
        return err
    drive_service = ctx.request_context.lifespan_context.drive_service
    successes: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []

    for recipient in recipients:
        email_address = recipient.get("email_address")
        role = recipient.get("role", "writer")

        if not email_address:
            failures.append({"email_address": None, "error": "Missing email_address"})
            continue
        if role not in ["reader", "commenter", "writer"]:
            failures.append(
                {
                    "email_address": email_address,
                    "error": f"Invalid role '{role}'",
                }
            )
            continue

        try:
            result = (
                drive_service.permissions()
                .create(
                    fileId=spreadsheet_id,
                    body={
                        "type": "user",
                        "role": role,
                        "emailAddress": email_address,
                    },
                    sendNotificationEmail=send_notification,
                    fields="id",
                )
                .execute()
            )
            successes.append(
                {
                    "email_address": email_address,
                    "role": role,
                    "permissionId": result.get("id"),
                }
            )
        except HttpError as e:
            failures.append(
                {
                    "email_address": email_address,
                    "error": sanitize_http_error(e, "Share spreadsheet"),
                }
            )

    return {"successes": successes, "failures": failures}


def search_spreadsheets(
    query: str,
    folder_id: Optional[str] = None,
    page_token: Optional[str] = None,
    max_results: int = 20,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Search for spreadsheets in Google Drive by name or content."""
    if not query or not query.strip():
        return {"error": "query must be a non-empty string"}

    drive_service = ctx.request_context.lifespan_context.drive_service
    max_results = min(max(1, max_results), 100)

    safe_query = escape_drive_value(query)
    search_query = (
        f"mimeType='application/vnd.google-apps.spreadsheet' and "
        f"(name contains '{safe_query}' or fullText contains '{safe_query}')"
    )
    if folder_id:
        search_query += (
            f" and '{escape_drive_value(folder_id)}' in parents"
        )

    list_kwargs: Dict[str, Any] = {
        "q": search_query,
        "pageSize": max_results,
        "spaces": "drive",
        "includeItemsFromAllDrives": True,
        "supportsAllDrives": True,
        "fields": (
            "nextPageToken, "
            "files(id, name, createdTime, modifiedTime, owners, webViewLink)"
        ),
        "orderBy": "modifiedTime desc",
    }
    if page_token:
        list_kwargs["pageToken"] = page_token

    results = (
        drive_service.files()
        .list(**list_kwargs)
        .execute()
    )

    items = [
        {
            "id": f["id"],
            "name": f["name"],
            "created_time": f.get("createdTime"),
            "modified_time": f.get("modifiedTime"),
            "owners": [o.get("emailAddress") for o in f.get("owners", [])],
            "web_link": f.get("webViewLink"),
        }
        for f in results.get("files", [])
    ]

    return {
        "items": items,
        "next_page_token": results.get("nextPageToken"),
    }


def register(registry: ToolRegistry) -> None:
    """Register all Sheets management tools in the registry."""
    registry.register(
        name="create_spreadsheet",
        description="Create a new Google Spreadsheet in the configured Drive folder.",
        parameters=[
            ToolParameter("title", "string", "Title for the new spreadsheet"),
            ToolParameter(
                "folder_id",
                "string",
                "Drive folder ID. Uses default if omitted.",
                required=False,
            ),
        ],
        tags=["sheets", "create", "spreadsheet", "new", "drive"],
        fn=create_spreadsheet,
    )

    registry.register(
        name="create_sheet",
        description="Add a new sheet/tab to an existing spreadsheet.",
        parameters=[
            ToolParameter(
                "spreadsheet_id",
                "string",
                "The ID of the spreadsheet (from URL)",
            ),
            ToolParameter("title", "string", "Name for the new sheet tab"),
        ],
        tags=["sheets", "create", "sheet", "tab", "add", "new"],
        fn=create_sheet,
    )

    registry.register(
        name="list_spreadsheets",
        description="List all spreadsheets in a Google Drive folder.",
        parameters=[
            ToolParameter(
                "folder_id",
                "string",
                "Drive folder ID. Uses default if omitted.",
                required=False,
            ),
        ],
        tags=["sheets", "list", "spreadsheets", "drive", "browse", "files"],
        fn=list_spreadsheets,
        read_only=True,
    )

    registry.register(
        name="list_sheets",
        description="List all sheet/tab names within a spreadsheet.",
        parameters=[
            ToolParameter(
                "spreadsheet_id",
                "string",
                "The ID of the spreadsheet (from URL)",
            ),
        ],
        tags=["sheets", "list", "sheets", "tabs", "names"],
        fn=list_sheets,
        read_only=True,
    )

    registry.register(
        name="list_folders",
        description=(
            "List folders in Google Drive. Searches root if no parent specified."
        ),
        parameters=[
            ToolParameter(
                "parent_folder_id",
                "string",
                "Parent folder ID. Searches root if omitted.",
                required=False,
            ),
        ],
        tags=["sheets", "list", "folders", "drive", "browse", "directory"],
        fn=list_folders,
        read_only=True,
    )

    registry.register(
        name="copy_sheet",
        description=(
            "Copy a sheet/tab from one spreadsheet to another, optionally renaming it."
        ),
        parameters=[
            ToolParameter("src_spreadsheet", "string", "Source spreadsheet ID"),
            ToolParameter("src_sheet", "string", "Source sheet/tab name"),
            ToolParameter("dst_spreadsheet", "string", "Destination spreadsheet ID"),
            ToolParameter(
                "dst_sheet",
                "string",
                "Name for the copied sheet in destination",
            ),
        ],
        tags=["sheets", "copy", "sheet", "duplicate", "transfer"],
        fn=copy_sheet,
    )

    registry.register(
        name="rename_sheet",
        description="Rename a sheet/tab in a spreadsheet.",
        parameters=[
            ToolParameter("spreadsheet", "string", "The spreadsheet ID"),
            ToolParameter("sheet", "string", "Current sheet/tab name"),
            ToolParameter("new_name", "string", "New sheet/tab name"),
        ],
        tags=["sheets", "rename", "sheet", "tab", "name", "update"],
        fn=rename_sheet,
    )

    registry.register(
        name="share_spreadsheet",
        description=(
            "Share a spreadsheet with users via email "
            "with specified roles (reader/commenter/writer)."
        ),
        parameters=[
            ToolParameter(
                "spreadsheet_id",
                "string",
                "The ID of the spreadsheet (from URL)",
            ),
            ToolParameter(
                "recipients",
                "array",
                "List of {email_address, role} objects. Role: reader/commenter/writer.",
            ),
            ToolParameter(
                "send_notification",
                "boolean",
                "Send email notification (default: true)",
                required=False,
                default=True,
            ),
        ],
        tags=["sheets", "share", "permissions", "access", "email", "collaborate"],
        fn=share_spreadsheet,
    )

    registry.register(
        name="search_spreadsheets",
        description=(
            "Search for spreadsheets in Google Drive by name or content. "
            "Supports pagination via page_token for large result sets."
        ),
        parameters=[
            ToolParameter(
                "query",
                "string",
                "Search query string (searches name and content)",
            ),
            ToolParameter(
                "folder_id",
                "string",
                "Restrict search to a specific Drive folder.",
                required=False,
            ),
            ToolParameter(
                "page_token",
                "string",
                "Token for fetching the next page of results.",
                required=False,
            ),
            ToolParameter(
                "max_results",
                "integer",
                "Max results per page (default: 20, max: 100)",
                required=False,
                default=20,
            ),
        ],
        tags=["sheets", "search", "find", "spreadsheets", "drive", "query"],
        fn=search_spreadsheets,
        read_only=True,
    )

    registry.register(
        name="delete_sheet",
        description="Delete a sheet/tab from a spreadsheet.",
        parameters=[
            ToolParameter(
                "spreadsheet_id",
                "string",
                "The ID of the spreadsheet (from URL)",
            ),
            ToolParameter("sheet", "string", "The sheet/tab name to delete"),
        ],
        tags=["sheets", "delete", "sheet", "tab", "remove"],
        fn=delete_sheet,
    )

    registry.register(
        name="duplicate_spreadsheet",
        description=(
            "Duplicate an entire spreadsheet. "
            "Optionally rename and place in a specific folder."
        ),
        parameters=[
            ToolParameter(
                "spreadsheet_id",
                "string",
                "The ID of the spreadsheet to duplicate",
            ),
            ToolParameter(
                "new_title",
                "string",
                "Title for the copy. Uses original name if omitted.",
                required=False,
            ),
            ToolParameter(
                "folder_id",
                "string",
                "Drive folder ID for the copy. Uses same folder if omitted.",
                required=False,
            ),
        ],
        tags=["sheets", "duplicate", "copy", "spreadsheet", "clone"],
        fn=duplicate_spreadsheet,
    )

    registry.register(
        name="move_spreadsheet",
        description="Move a spreadsheet to a different Google Drive folder.",
        parameters=[
            ToolParameter(
                "spreadsheet_id",
                "string",
                "The ID of the spreadsheet to move",
            ),
            ToolParameter(
                "destination_folder_id",
                "string",
                "The target Drive folder ID",
            ),
        ],
        tags=["sheets", "move", "spreadsheet", "folder", "drive", "organize"],
        fn=move_spreadsheet,
    )
