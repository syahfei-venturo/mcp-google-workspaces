#!/usr/bin/env python
"""
Google Workspace MCP Server

Exposes two meta-tools (search_tools, execute) that provide
access to all Google Workspace operations (Sheets, Docs) through
a tool registry with fuzzy search. This reduces context window usage
from ~13K tokens to ~2K tokens while maintaining full functionality.

Usage flow for agents:
  1. search_tools("read data") -> discover relevant tools + parameters
  2. execute("data = get_sheet_data(spreadsheet_id='...', sheet='...')")
"""

import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP, Context

from .auth import workspace_lifespan
from .registry import ToolRegistry
from .sandbox import execute_script
from .tools import register_all_tools

logger = logging.getLogger(__name__)


def _parse_enabled_tools() -> Optional[set]:
    """Parse enabled tools from env var or --include-tools CLI arg."""
    enabled_tools_str = None
    for i, arg in enumerate(sys.argv):
        if arg == "--include-tools" and i + 1 < len(sys.argv):
            enabled_tools_str = sys.argv[i + 1]
            break

    if not enabled_tools_str:
        enabled_tools_str = os.environ.get("ENABLED_TOOLS")

    if not enabled_tools_str:
        return None

    tools = {t.strip() for t in enabled_tools_str.split(",") if t.strip()}
    return tools if tools else None


# Build the internal tool registry
registry = ToolRegistry()
register_all_tools(registry, _parse_enabled_tools())

# Resolve host/port from environment
_host = os.environ.get("HOST") or os.environ.get("FASTMCP_HOST") or "0.0.0.0"
_port_str = os.environ.get("PORT") or os.environ.get("FASTMCP_PORT") or "8000"
try:
    _port = int(_port_str)
except ValueError:
    _port = 8000

# Initialize MCP server — only 2 tools exposed
mcp = FastMCP(
    "Google Workspace",
    dependencies=[
        "google-auth",
        "google-auth-oauthlib",
        "google-api-python-client",
    ],
    lifespan=workspace_lifespan,
    host=_host,
    port=_port,
)


@mcp.tool()
def read_me() -> str:
    """
    Returns a guide on how to use this Google Workspace MCP server.
    Call this first if you are unsure how to interact with the server.

    Returns:
        A markdown-formatted usage guide covering available tools,
        workflow, and examples.
    """
    tool_count = len(registry.tool_names)
    categories = registry.categories

    return f"""# Google Workspace MCP Server

## Overview
This server exposes Google Sheets and Google Docs operations through
three meta-tools: `read_me`, `search_tools`, and `execute`.
There are currently **{tool_count} tools** registered across categories: {", ".join(categories)}.

## Workflow

1. **read_me()** — Start here. Get this guide.
2. **search_tools(query)** — Discover tools by name, description, or functionality.
3. **execute(code)** — Run Python code that calls the discovered tools.

## search_tools

```python
search_tools(query="read data", limit=5, category="sheets")
```

- `query`: Natural language or keyword. Fuzzy-matched against tool names, descriptions, and tags.
- `limit`: Max results (default 5).
- `category`: Filter by `"sheets"` or `"docs"`. Leave empty to search all.

Returns a list of tools with their parameter schemas.

## execute

```python
execute(code=\"\"\"
data = get_sheet_data(spreadsheet_id="abc123", sheet="Sheet1")
data
\"\"\")
```

- `code`: Python source. All registered tools are available as functions.
- Safe imports available: `json`, `math`, `datetime`, `re`, `collections`, `itertools`.
- Dangerous imports (os, sys, subprocess, socket) are blocked.
- `timeout`: Max seconds (default 30).
- `memory_limit_mb`: Memory cap (default 256).

Returns: `{{output, result, tool_calls, error}}`.

## Example — Read a spreadsheet

```python
# Step 1: discover
search_tools("read spreadsheet data")

# Step 2: execute
execute(\"\"\"
rows = get_sheet_data(spreadsheet_id="YOUR_ID", sheet="Sheet1")
rows
\"\"\")
```

## Example — Write to a Google Doc

```python
# Step 1: discover
search_tools("insert text document", category="docs")

# Step 2: execute
execute(\"\"\"
insert_text_with_html(document_id="YOUR_DOC_ID", html_content="<p>Hello World</p>")
\"\"\")
```

## Available Categories
{chr(10).join(f"- **{cat}**" for cat in categories)}

Use `search_tools(query="", category="<name>")` to list all tools in a category.
"""


@mcp.tool()
def search_tools(
    query: str,
    limit: int = 5,
    category: str = "",
    ctx: Optional[Context] = None,
) -> List[Dict[str, Any]]:
    """
    Search for available Google Workspace tools by name, description, or functionality.
    Uses fuzzy matching to find relevant tools. Call this before execute()
    to discover available tools and their required parameters.

    Supports both Google Sheets and Google Docs tools.

    Args:
        query: Search query. Fuzzy-matched against tool names, descriptions, and tags.
               Examples: "read data", "update cells", "create spreadsheet", "chart",
                         "docs insert text", "sheets format", "create document"
        limit: Maximum number of results to return (default: 5)
        category: Filter by service category (e.g. "sheets", "docs").
                  Leave empty to search across all categories.

    Returns:
        List of matching tools with name, description, category, parameters schema,
        and relevance score.
        Use the returned parameter schemas to write Python code for execute().
    """
    return registry.search(query, limit, category=category if category else None)


@mcp.tool()
def execute(
    code: str,
    timeout: int = 30,
    memory_limit_mb: int = 256,
    ctx: Optional[Context] = None,
) -> Any:
    """
    Execute a Python script in a sandboxed environment with all
    registered Google Workspace tools available as callable functions.

    Use search_tools first to discover available tools, then write
    Python code that calls them directly by name with keyword arguments.

    The sandbox provides:
    - All registered tools as Python functions (call by name, keyword args)
    - Safe imports: json, math, datetime, re, collections, itertools, etc.
    - print() output capture
    - Last expression value captured as the result

    The sandbox blocks:
    - Dangerous imports (os, sys, subprocess, socket, etc.)
    - File system access, network access, threading
    - Dunder attribute access (__class__, __dict__, etc.)

    Example — single tool call:
        data = get_sheet_data(spreadsheet_id="abc", sheet="Sheet1")
        data

    Example — multi-step orchestration:
        data = get_sheet_data(spreadsheet_id="abc", sheet="Sheet1")
        rows = data.get("values", [])
        totals = []
        for row in rows[1:]:
            totals.append([row[0], sum(float(x) for x in row[1:])])
        update_cells(
            spreadsheet_id="abc",
            sheet="Sheet1",
            range="D2:E" + str(len(totals) + 1),
            data=totals,
        )

    Args:
        code: Python source code to execute. All tools from search_tools
              are available as functions — call them with keyword arguments.
        timeout: Maximum execution time in seconds (1-300, default: 30).
        memory_limit_mb: Memory limit in MB (64-1024, default: 256).

    Returns:
        Dict with output (stdout), result (last expression value),
        tool_calls (list of tools invoked), and error (if any).
    """
    return execute_script(
        code=code,
        registry=registry,
        ctx=ctx,
        timeout=timeout,
        memory_limit_mb=memory_limit_mb,
    )


# MCP Resource — kept as direct resource, not part of tool registry
@mcp.resource("spreadsheet://{spreadsheet_id}/info")
def get_spreadsheet_info(spreadsheet_id: str) -> str:
    """Get basic information about a Google Spreadsheet."""
    context = mcp.get_lifespan_context()
    sheets_service = context.sheets_service

    spreadsheet = (
        sheets_service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    )
    info = {
        "title": spreadsheet.get("properties", {}).get("title", "Unknown"),
        "sheets": [
            {
                "title": s["properties"]["title"],
                "sheetId": s["properties"]["sheetId"],
                "gridProperties": s["properties"].get("gridProperties", {}),
            }
            for s in spreadsheet.get("sheets", [])
        ],
    }
    return json.dumps(info, indent=2)


def main():
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    tool_count = len(registry.tool_names)
    logger.info("Tool registry: %d tools registered", tool_count)
    logger.info("Registered tools: %s", ", ".join(sorted(registry.tool_names)))
    logger.info("MCP exposes 2 meta-tools: search_tools, execute")

    transport = "stdio"
    for i, arg in enumerate(sys.argv):
        if arg == "--transport" and i + 1 < len(sys.argv):
            transport = sys.argv[i + 1]
            break

    mcp.run(transport=transport)
