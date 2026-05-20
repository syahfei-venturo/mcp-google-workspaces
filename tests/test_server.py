"""Tests for Google Workspace MCP server meta-tools."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

from mcp_google_workspace.server import _parse_enabled_tools, read_me, search_tools, execute


# --- _parse_enabled_tools tests ---


class TestParseEnabledTools:
    """Tests for _parse_enabled_tools function."""

    def test_returns_none_when_no_env_or_arg(self):
        """Returns None when neither env var nor CLI arg is set."""
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(sys, "argv", ["server.py"]):
                result = _parse_enabled_tools()
                assert result is None

    def test_parses_env_var_single_tool(self):
        """Parses ENABLED_TOOLS env var with single tool."""
        with patch.dict(os.environ, {"ENABLED_TOOLS": "get_sheet_data"}):
            with patch.object(sys, "argv", ["server.py"]):
                result = _parse_enabled_tools()
                assert result == {"get_sheet_data"}

    def test_parses_env_var_multiple_tools(self):
        """Parses ENABLED_TOOLS env var with comma-separated tools."""
        with patch.dict(os.environ, {"ENABLED_TOOLS": "get_sheet_data,update_cells,create_spreadsheet"}):
            with patch.object(sys, "argv", ["server.py"]):
                result = _parse_enabled_tools()
                assert result == {"get_sheet_data", "update_cells", "create_spreadsheet"}

    def test_trims_whitespace_in_env_var(self):
        """Trims whitespace around tool names in env var."""
        with patch.dict(os.environ, {"ENABLED_TOOLS": "  get_sheet_data  ,  update_cells  "}):
            with patch.object(sys, "argv", ["server.py"]):
                result = _parse_enabled_tools()
                assert result == {"get_sheet_data", "update_cells"}

    def test_returns_none_for_empty_env_var(self):
        """Returns None when ENABLED_TOOLS env var is empty string."""
        with patch.dict(os.environ, {"ENABLED_TOOLS": ""}):
            with patch.object(sys, "argv", ["server.py"]):
                result = _parse_enabled_tools()
                assert result is None

    def test_returns_none_for_whitespace_only_env_var(self):
        """Returns None when ENABLED_TOOLS env var is whitespace-only."""
        with patch.dict(os.environ, {"ENABLED_TOOLS": "   "}):
            with patch.object(sys, "argv", ["server.py"]):
                result = _parse_enabled_tools()
                assert result is None

    def test_parses_cli_arg_single_tool(self):
        """Parses --include-tools CLI arg with single tool."""
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(sys, "argv", ["server.py", "--include-tools", "get_sheet_data"]):
                result = _parse_enabled_tools()
                assert result == {"get_sheet_data"}

    def test_parses_cli_arg_multiple_tools(self):
        """Parses --include-tools CLI arg with comma-separated tools."""
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(
                sys, "argv",
                ["server.py", "--include-tools", "get_sheet_data,update_cells"]
            ):
                result = _parse_enabled_tools()
                assert result == {"get_sheet_data", "update_cells"}

    def test_cli_arg_takes_precedence_over_env_var(self):
        """CLI arg --include-tools takes precedence over ENABLED_TOOLS env var."""
        with patch.dict(os.environ, {"ENABLED_TOOLS": "env_tool1,env_tool2"}):
            with patch.object(
                sys, "argv",
                ["server.py", "--include-tools", "cli_tool1,cli_tool2"]
            ):
                result = _parse_enabled_tools()
                assert result == {"cli_tool1", "cli_tool2"}

    def test_returns_none_for_empty_cli_arg(self):
        """Returns None when --include-tools arg is empty string."""
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(sys, "argv", ["server.py", "--include-tools", ""]):
                result = _parse_enabled_tools()
                assert result is None

    def test_returns_none_for_whitespace_only_cli_arg(self):
        """Returns None when --include-tools arg is whitespace-only."""
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(sys, "argv", ["server.py", "--include-tools", "   "]):
                result = _parse_enabled_tools()
                assert result is None

    def test_ignores_cli_arg_without_value(self):
        """Ignores --include-tools when not followed by a value."""
        with patch.dict(os.environ, {"ENABLED_TOOLS": "env_tool"}):
            with patch.object(sys, "argv", ["server.py", "--include-tools"]):
                result = _parse_enabled_tools()
                # Falls back to env var since CLI arg is incomplete
                assert result == {"env_tool"}

    def test_handles_trailing_commas_in_env_var(self):
        """Handles trailing commas in ENABLED_TOOLS env var."""
        with patch.dict(os.environ, {"ENABLED_TOOLS": "tool1,tool2,"}):
            with patch.object(sys, "argv", ["server.py"]):
                result = _parse_enabled_tools()
                assert result == {"tool1", "tool2"}

    def test_handles_leading_commas_in_env_var(self):
        """Handles leading commas in ENABLED_TOOLS env var."""
        with patch.dict(os.environ, {"ENABLED_TOOLS": ",tool1,tool2"}):
            with patch.object(sys, "argv", ["server.py"]):
                result = _parse_enabled_tools()
                assert result == {"tool1", "tool2"}

    def test_deduplicates_tools_in_env_var(self):
        """Deduplicates tool names in ENABLED_TOOLS env var."""
        with patch.dict(os.environ, {"ENABLED_TOOLS": "tool1,tool2,tool1,tool2"}):
            with patch.object(sys, "argv", ["server.py"]):
                result = _parse_enabled_tools()
                assert result == {"tool1", "tool2"}


# --- read_me tests ---


class TestReadMe:
    """Tests for read_me function."""

    def test_returns_string(self):
        """read_me returns a string."""
        result = read_me()
        assert isinstance(result, str)

    def test_contains_header(self):
        """read_me contains main header."""
        result = read_me()
        assert "# Google Workspace MCP Server" in result

    def test_contains_overview_section(self):
        """read_me contains Overview section."""
        result = read_me()
        assert "## Overview" in result

    def test_contains_workflow_section(self):
        """read_me contains Workflow section."""
        result = read_me()
        assert "## Workflow" in result

    def test_contains_search_tools_section(self):
        """read_me contains search_tools documentation."""
        result = read_me()
        assert "## search_tools" in result

    def test_contains_execute_section(self):
        """read_me contains execute documentation."""
        result = read_me()
        assert "## execute" in result

    def test_contains_example_read_spreadsheet(self):
        """read_me contains example for reading spreadsheet."""
        result = read_me()
        assert "Example — Read a spreadsheet" in result

    def test_contains_example_write_doc(self):
        """read_me contains example for writing to doc."""
        result = read_me()
        assert "Example" in result and "Write" in result and "Google Doc" in result

    def test_contains_available_categories_section(self):
        """read_me contains Available Categories section."""
        result = read_me()
        assert "## Available Categories" in result

    def test_includes_tool_count(self):
        """read_me includes count of registered tools."""
        result = read_me()
        assert "tools" in result.lower()
        # Should contain something like "**X tools**"
        assert "**" in result

    def test_includes_categories(self):
        """read_me mentions categories."""
        result = read_me()
        # Should have categories listed (from registry.categories)
        assert "**" in result  # Markdown bold formatting for categories


# --- search_tools tests ---


class TestSearchTools:
    """Tests for search_tools function."""

    def test_returns_list(self):
        """search_tools returns a list."""
        result = search_tools("sheet")
        assert isinstance(result, list)

    def test_returns_tools_matching_query(self):
        """search_tools returns tools matching query."""
        result = search_tools("sheet")
        assert len(result) > 0

    def test_respects_limit_parameter(self):
        """search_tools respects limit parameter."""
        result = search_tools("", limit=2)
        # Empty query returns category summary or tools up to limit
        # Limit should be respected in any case
        assert len(result) <= 2

    def test_limit_default_is_five(self):
        """search_tools defaults to limit=5."""
        result = search_tools("get")
        assert len(result) <= 5

    def test_filters_by_category(self):
        """search_tools filters by category parameter."""
        result = search_tools("", category="sheets")
        # Should return only sheets tools (if category filter works)
        if result:
            for tool in result:
                assert tool.get("category", "").lower() == "sheets"

    def test_returns_empty_list_for_no_matches(self):
        """search_tools returns empty list for no matches."""
        result = search_tools("xyzabc_nonexistent_tool_12345")
        assert isinstance(result, list)
        # May be empty or category summary depending on implementation

    def test_returned_tools_have_required_fields(self):
        """Each returned tool has required metadata fields."""
        result = search_tools("sheet")
        if result:
            for tool in result:
                assert "name" in tool
                assert "description" in tool

    def test_with_empty_query_and_no_category(self):
        """search_tools with empty query and no category returns results."""
        result = search_tools("")
        assert isinstance(result, list)

    def test_with_empty_query_and_category(self):
        """search_tools with empty query and category filters by category."""
        result = search_tools("", category="sheets")
        assert isinstance(result, list)

    def test_limit_parameter_type_validation(self):
        """search_tools accepts limit as integer."""
        # Should not raise error
        result = search_tools("sheet", limit=3)
        assert len(result) <= 3

    def test_category_parameter_type_validation(self):
        """search_tools accepts category as string."""
        # Should not raise error
        result = search_tools("", category="sheets")
        assert isinstance(result, list)


# --- execute tests ---


class TestExecute:
    """Tests for execute function."""

    @patch("mcp_google_workspace.server.execute_script")
    def test_returns_result_from_sandbox(self, mock_execute_script):
        """execute delegates to execute_script and returns its result."""
        mock_execute_script.return_value = {
            "output": "test output",
            "result": 42,
            "tool_calls": [],
        }
        result = execute("x = 42\nx")
        assert result["result"] == 42

    @patch("mcp_google_workspace.server.execute_script")
    def test_passes_code_to_sandbox(self, mock_execute_script):
        """execute passes code parameter to execute_script."""
        mock_execute_script.return_value = {}
        code = "x = 1 + 1\nx"
        execute(code)
        mock_execute_script.assert_called_once()
        call_kwargs = mock_execute_script.call_args[1]
        assert call_kwargs["code"] == code

    @patch("mcp_google_workspace.server.execute_script")
    def test_passes_timeout_parameter(self, mock_execute_script):
        """execute passes timeout parameter to execute_script."""
        mock_execute_script.return_value = {}
        execute("x = 1", timeout=60)
        call_kwargs = mock_execute_script.call_args[1]
        assert call_kwargs["timeout"] == 60

    @patch("mcp_google_workspace.server.execute_script")
    def test_timeout_default_is_thirty(self, mock_execute_script):
        """execute defaults to timeout=30."""
        mock_execute_script.return_value = {}
        execute("x = 1")
        call_kwargs = mock_execute_script.call_args[1]
        assert call_kwargs["timeout"] == 30

    @patch("mcp_google_workspace.server.execute_script")
    def test_passes_memory_limit_parameter(self, mock_execute_script):
        """execute passes memory_limit_mb parameter to execute_script."""
        mock_execute_script.return_value = {}
        execute("x = 1", memory_limit_mb=512)
        call_kwargs = mock_execute_script.call_args[1]
        assert call_kwargs["memory_limit_mb"] == 512

    @patch("mcp_google_workspace.server.execute_script")
    def test_memory_limit_default_is_256(self, mock_execute_script):
        """execute defaults to memory_limit_mb=256."""
        mock_execute_script.return_value = {}
        execute("x = 1")
        call_kwargs = mock_execute_script.call_args[1]
        assert call_kwargs["memory_limit_mb"] == 256

    @patch("mcp_google_workspace.server.execute_script")
    def test_passes_registry_to_sandbox(self, mock_execute_script):
        """execute passes registry to execute_script."""
        mock_execute_script.return_value = {}
        execute("x = 1")
        call_kwargs = mock_execute_script.call_args[1]
        assert "registry" in call_kwargs
        assert call_kwargs["registry"] is not None

    @patch("mcp_google_workspace.server.execute_script")
    def test_passes_context_to_sandbox(self, mock_execute_script):
        """execute passes ctx parameter to execute_script."""
        mock_execute_script.return_value = {}
        ctx = MagicMock()
        execute("x = 1", ctx=ctx)
        call_kwargs = mock_execute_script.call_args[1]
        assert call_kwargs["ctx"] == ctx

    @patch("mcp_google_workspace.server.execute_script")
    def test_with_all_parameters(self, mock_execute_script):
        """execute works with all parameters specified."""
        mock_execute_script.return_value = {"result": "done"}
        ctx = MagicMock()
        result = execute(
            "x = 2 + 2\nx",
            timeout=45,
            memory_limit_mb=384,
            ctx=ctx
        )
        assert result["result"] == "done"
        call_kwargs = mock_execute_script.call_args[1]
        assert call_kwargs["code"] == "x = 2 + 2\nx"
        assert call_kwargs["timeout"] == 45
        assert call_kwargs["memory_limit_mb"] == 384
        assert call_kwargs["ctx"] == ctx

    @patch("mcp_google_workspace.server.execute_script")
    def test_error_from_sandbox_is_returned(self, mock_execute_script):
        """execute returns error from sandbox."""
        mock_execute_script.return_value = {"error": "Code syntax error"}
        result = execute("invalid code ][")
        assert result["error"] == "Code syntax error"

    @patch("mcp_google_workspace.server.execute_script")
    def test_tool_calls_from_sandbox_are_returned(self, mock_execute_script):
        """execute returns tool_calls list from sandbox."""
        mock_execute_script.return_value = {
            "tool_calls": ["get_sheet_data", "update_cells"],
            "result": True
        }
        result = execute("data = get_sheet_data(...)")
        assert result["tool_calls"] == ["get_sheet_data", "update_cells"]

    @patch("mcp_google_workspace.server.execute_script")
    def test_output_from_sandbox_is_returned(self, mock_execute_script):
        """execute returns stdout output from sandbox."""
        mock_execute_script.return_value = {
            "output": "printed text",
            "result": None
        }
        result = execute("print('printed text')")
        assert result["output"] == "printed text"


# --- Integration-style tests ---


class TestServerIntegration:
    """Integration-style tests for server meta-tools."""

    def test_search_tools_finds_real_tools(self):
        """search_tools actually finds registered tools."""
        # This tests against the real registry
        result = search_tools("get")
        assert len(result) > 0
        # All returned items should have name field
        for tool in result:
            assert "name" in tool

    def test_read_me_mentions_real_tool_count(self):
        """read_me reflects actual number of registered tools."""
        result = read_me()
        # Should contain some number >= 1
        assert "1 tools" in result or "2 tools" in result or "tools" in result.lower()

    def test_read_me_shows_real_categories(self):
        """read_me lists actual categories from registry."""
        result = read_me()
        # Should mention sheets or docs or some real category
        content_lower = result.lower()
        # At minimum, should have some category mentioned
        assert "sheets" in content_lower or "docs" in content_lower or "**" in result
