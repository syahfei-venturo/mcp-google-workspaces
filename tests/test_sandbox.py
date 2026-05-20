"""Tests for the sandboxed script execution engine."""

import multiprocessing
import time

import pytest

from mcp_google_workspace.registry import ToolParameter, ToolRegistry
from mcp_google_workspace.sandbox import (
    ALLOWED_MODULES,
    BLOCKED_MODULES,
    DEFAULT_TIMEOUT_SECONDS,
    MAX_CODE_BYTES,
    _ensure_serializable,
    _wrap_last_expression,
    execute_script,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_tool(name, fn, description="test tool", params=None):
    """Helper to register a single tool in a fresh registry."""
    registry = ToolRegistry()
    registry.register(
        name=name,
        description=description,
        parameters=params or [],
        tags=[name],
        fn=fn,
        category="test",
    )
    return registry


def _make_registry_with_tools(**tools):
    """Create a registry with multiple named tool functions."""
    registry = ToolRegistry()
    for name, fn in tools.items():
        registry.register(
            name=name,
            description=f"Test tool: {name}",
            parameters=[
                ToolParameter("value", "string", "test param", required=False),
            ],
            tags=[name],
            fn=fn,
            category="test",
        )
    return registry


class _FakeCtx:
    """Minimal context stub for tool calls that don't use ctx."""

    pass


CTX = _FakeCtx()


# ---------------------------------------------------------------------------
# AST helper tests
# ---------------------------------------------------------------------------


class TestWrapLastExpression:
    def test_wraps_bare_expression(self):
        result = _wrap_last_expression("x = 1\nx + 2")
        assert "sandbox_result" in result

    def test_wraps_simple_assignment(self):
        source = "x = 42"
        result = _wrap_last_expression(source)
        assert "sandbox_result = x" in result

    def test_no_wrap_multi_target_assignment(self):
        source = "a = b = 42"
        result = _wrap_last_expression(source)
        assert "sandbox_result" not in result

    def test_no_wrap_tuple_unpack_assignment(self):
        source = "a, b = 1, 2"
        result = _wrap_last_expression(source)
        assert "sandbox_result" not in result

    def test_no_wrap_function_def(self):
        source = "def foo(): pass"
        result = _wrap_last_expression(source)
        assert "sandbox_result" not in result

    def test_empty_source(self):
        assert _wrap_last_expression("") == ""

    def test_syntax_error_returns_original(self):
        bad = "def ("
        assert _wrap_last_expression(bad) == bad

    def test_single_expression(self):
        result = _wrap_last_expression("42")
        assert "sandbox_result" in result


# ---------------------------------------------------------------------------
# Serialization helper tests
# ---------------------------------------------------------------------------


class TestEnsureSerializable:
    def test_dict_passes(self):
        d = {"a": 1, "b": [2, 3]}
        assert _ensure_serializable(d) == d

    def test_none_passes(self):
        assert _ensure_serializable(None) is None

    def test_non_serializable_becomes_string(self):
        result = _ensure_serializable(object())
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Basic script execution
# ---------------------------------------------------------------------------


class TestBasicExecution:
    def test_simple_print(self):
        registry = ToolRegistry()
        result = execute_script("print('hello')", registry, CTX, timeout=10)
        assert result.get("error") is None
        assert "hello" in result["output"]

    def test_result_capture(self):
        registry = ToolRegistry()
        result = execute_script("x = 10\nx * 2", registry, CTX, timeout=10)
        assert result.get("error") is None
        assert result["result"] == 20

    def test_multiline_script(self):
        registry = ToolRegistry()
        code = "nums = [1, 2, 3, 4, 5]\ntotal = sum(nums)\nprint(f'total={total}')\ntotal"
        result = execute_script(code, registry, CTX, timeout=10)
        assert result.get("error") is None
        assert "total=15" in result["output"]
        assert result["result"] == 15

    def test_empty_code_returns_error(self):
        registry = ToolRegistry()
        result = execute_script("", registry, CTX)
        assert "error" in result

    def test_whitespace_only_returns_error(self):
        registry = ToolRegistry()
        result = execute_script("   \n  ", registry, CTX)
        assert "error" in result

    def test_code_too_large(self):
        registry = ToolRegistry()
        code = "x = 1\n" * (MAX_CODE_BYTES + 1)
        result = execute_script(code, registry, CTX)
        assert "error" in result
        assert "maximum size" in result["error"].lower() or "exceeds" in result["error"].lower()


# ---------------------------------------------------------------------------
# Tool invocation from scripts
# ---------------------------------------------------------------------------


class TestToolInvocation:
    def test_call_tool(self):
        call_log = []

        def mock_tool(value="default", ctx=None):
            call_log.append(value)
            return {"data": value}

        registry = _make_tool("my_tool", mock_tool, params=[
            ToolParameter("value", "string", "a value", required=False),
        ])
        code = "result = my_tool(value='test123')\nprint(result)"
        result = execute_script(code, registry, CTX, timeout=15)
        assert result.get("error") is None
        tool_names = [tc["tool"] for tc in result.get("tool_calls", [])]
        assert "my_tool" in tool_names

    def test_tool_error_propagates(self):
        def failing_tool(ctx=None):
            raise ValueError("something broke")

        registry = _make_tool("bad_tool", failing_tool)
        code = "bad_tool()"
        result = execute_script(code, registry, CTX, timeout=10)
        assert "error" in result
        assert "something broke" in result["error"]

    def test_unknown_tool_is_name_error(self):
        registry = ToolRegistry()
        code = "nonexistent_tool()"
        result = execute_script(code, registry, CTX, timeout=10)
        assert "error" in result

    def test_multiple_tool_calls(self):
        call_count = {"n": 0}

        def counter(ctx=None):
            call_count["n"] += 1
            return {"count": call_count["n"]}

        registry = _make_tool("inc", counter)
        code = "a = inc()\nb = inc()\nc = inc()\nprint(a, b, c)"
        result = execute_script(code, registry, CTX, timeout=15)
        assert result.get("error") is None
        assert len(result.get("tool_calls", [])) == 3

    def test_tool_result_used_in_logic(self):
        def get_data(ctx=None):
            return {"values": [[1, 2], [3, 4], [5, 6]]}

        registry = _make_tool("get_data", get_data)
        code = (
            "data = get_data()\n"
            "total = sum(row[0] + row[1] for row in data['values'])\n"
            "total"
        )
        result = execute_script(code, registry, CTX, timeout=15)
        assert result.get("error") is None
        assert result["result"] == 21


# ---------------------------------------------------------------------------
# Security: blocked imports
# ---------------------------------------------------------------------------


class TestBlockedImports:
    @pytest.mark.parametrize("module", ["os", "sys", "subprocess", "socket", "shutil"])
    def test_blocked_module(self, module):
        registry = ToolRegistry()
        code = f"import {module}"
        result = execute_script(code, registry, CTX, timeout=10)
        assert "error" in result
        assert "not allowed" in result["error"].lower() or "import" in result["error"].lower()

    def test_blocked_from_import(self):
        registry = ToolRegistry()
        code = "from os import path"
        result = execute_script(code, registry, CTX, timeout=10)
        assert "error" in result

    def test_blocked_importlib(self):
        registry = ToolRegistry()
        code = "import importlib"
        result = execute_script(code, registry, CTX, timeout=10)
        assert "error" in result


# ---------------------------------------------------------------------------
# Security: allowed imports
# ---------------------------------------------------------------------------


class TestAllowedImports:
    @pytest.mark.parametrize("module", ["json", "math", "re", "datetime", "collections"])
    def test_allowed_module(self, module):
        registry = ToolRegistry()
        code = f"import {module}\nprint(type({module}))"
        result = execute_script(code, registry, CTX, timeout=10)
        assert result.get("error") is None

    def test_json_usage(self):
        registry = ToolRegistry()
        code = "import json\ndata = json.dumps({'a': 1})\nprint(data)\ndata"
        result = execute_script(code, registry, CTX, timeout=10)
        assert result.get("error") is None
        assert '"a"' in result.get("output", "")

    def test_math_usage(self):
        registry = ToolRegistry()
        code = "import math\nmath.sqrt(144)"
        result = execute_script(code, registry, CTX, timeout=10)
        assert result.get("error") is None
        assert result["result"] == 12.0


# ---------------------------------------------------------------------------
# Security: restricted builtins
# ---------------------------------------------------------------------------


class TestRestrictedBuiltins:
    def test_dunder_access_blocked(self):
        registry = ToolRegistry()
        code = "x = ().__class__"
        result = execute_script(code, registry, CTX, timeout=10)
        assert "error" in result

    def test_open_not_available(self):
        registry = ToolRegistry()
        code = "f = open('/etc/passwd')"
        result = execute_script(code, registry, CTX, timeout=10)
        assert "error" in result


# ---------------------------------------------------------------------------
# Resource limits
# ---------------------------------------------------------------------------


class TestResourceLimits:
    def test_timeout_kills_infinite_loop(self):
        registry = ToolRegistry()
        code = "while True: pass"
        start = time.monotonic()
        result = execute_script(code, registry, CTX, timeout=3)
        elapsed = time.monotonic() - start
        assert "error" in result
        assert "timeout" in result["error"].lower() or "exceeded" in result["error"].lower()
        assert elapsed < 10  # Should not hang

    def test_timeout_parameter_respected(self):
        registry = ToolRegistry()
        code = "import time\ntime.sleep(20)"
        start = time.monotonic()
        result = execute_script(code, registry, CTX, timeout=2)
        elapsed = time.monotonic() - start
        assert elapsed < 8


# ---------------------------------------------------------------------------
# Syntax and runtime errors
# ---------------------------------------------------------------------------


class TestErrors:
    def test_syntax_error_reported(self):
        registry = ToolRegistry()
        code = "def ("
        result = execute_script(code, registry, CTX, timeout=10)
        assert "error" in result
        assert "syntax" in result["error"].lower()

    def test_runtime_error_reported(self):
        registry = ToolRegistry()
        code = "x = 1 / 0"
        result = execute_script(code, registry, CTX, timeout=10)
        assert "error" in result
        assert "ZeroDivision" in result["error"]

    def test_name_error_reported(self):
        registry = ToolRegistry()
        code = "undefined_var + 1"
        result = execute_script(code, registry, CTX, timeout=10)
        assert "error" in result

    def test_type_error_in_tool_call(self):
        def typed_tool(name: str, count: int, ctx=None):
            return {"name": name, "count": count}

        registry = _make_tool("typed_tool", typed_tool, params=[
            ToolParameter("name", "string", "a name"),
            ToolParameter("count", "integer", "a count"),
        ])
        # Missing required parameter -> TypeError
        code = "typed_tool()"
        result = execute_script(code, registry, CTX, timeout=10)
        assert "error" in result


# ---------------------------------------------------------------------------
# Help function
# ---------------------------------------------------------------------------


class TestHelpFunction:
    def test_help_lists_tools(self):
        def noop(ctx=None):
            return {}

        registry = _make_tool("my_tool", noop)
        code = "h = help()\nprint(h)"
        result = execute_script(code, registry, CTX, timeout=10)
        assert result.get("error") is None
        assert "my_tool" in result.get("output", "")

    def test_help_specific_tool(self):
        def noop(value="x", ctx=None):
            return {}

        registry = _make_tool(
            "detailed_tool",
            noop,
            description="A detailed test tool",
            params=[ToolParameter("value", "string", "a value", required=False)],
        )
        code = "h = help('detailed_tool')\nprint(h)"
        result = execute_script(code, registry, CTX, timeout=10)
        assert result.get("error") is None
        assert "detailed_tool" in result.get("output", "")

    def test_help_unknown_tool(self):
        registry = ToolRegistry()
        code = "h = help('nonexistent')\nprint(h)"
        result = execute_script(code, registry, CTX, timeout=10)
        assert result.get("error") is None
        assert "Unknown" in result.get("output", "") or "unknown" in result.get("output", "").lower()


# ---------------------------------------------------------------------------
# tools variable
# ---------------------------------------------------------------------------


class TestToolsVariable:
    def test_tools_list_available(self):
        def noop(ctx=None):
            return {}

        registry = _make_registry_with_tools(alpha=noop, beta=noop)
        code = "print(tools)"
        result = execute_script(code, registry, CTX, timeout=10)
        assert result.get("error") is None
        assert "alpha" in result.get("output", "")
        assert "beta" in result.get("output", "")


# ---------------------------------------------------------------------------
# Module-level constants sanity checks
# ---------------------------------------------------------------------------


class TestModuleConstants:
    def test_blocked_and_allowed_disjoint(self):
        overlap = BLOCKED_MODULES & ALLOWED_MODULES
        assert not overlap, f"Modules in both blocked and allowed: {overlap}"

    def test_common_dangerous_modules_blocked(self):
        for mod in ("os", "sys", "subprocess", "socket", "shutil", "pickle"):
            assert mod in BLOCKED_MODULES

    def test_common_safe_modules_allowed(self):
        for mod in ("json", "math", "re", "datetime", "collections"):
            assert mod in ALLOWED_MODULES


# ---------------------------------------------------------------------------
# LimitedWriter tests
# ---------------------------------------------------------------------------


class TestLimitedWriter:
    def test_basic_write(self):
        from mcp_google_workspace.sandbox import _LimitedWriter

        w = _LimitedWriter(max_bytes=100)
        n = w.write("hello")
        assert n == 5
        assert w.getvalue() == "hello"
        assert not w.truncated

    def test_truncation(self):
        from mcp_google_workspace.sandbox import _LimitedWriter

        w = _LimitedWriter(max_bytes=10)
        w.write("12345")
        n = w.write("67890EXTRA")
        assert w.truncated
        assert len(w.getvalue()) <= 10

    def test_write_after_truncation_returns_zero(self):
        from mcp_google_workspace.sandbox import _LimitedWriter

        w = _LimitedWriter(max_bytes=5)
        w.write("12345678")
        assert w.truncated
        assert w.write("more") == 0

    def test_stream_properties(self):
        from mcp_google_workspace.sandbox import _LimitedWriter

        w = _LimitedWriter()
        assert w.readable() is False
        assert w.writable() is True
        assert w.seekable() is False
        assert w.encoding == "utf-8"

    def test_flush_no_op(self):
        from mcp_google_workspace.sandbox import _LimitedWriter

        w = _LimitedWriter()
        w.write("data")
        w.flush()  # Should not raise
        assert w.getvalue() == "data"


# ---------------------------------------------------------------------------
# _inplacevar tests
# ---------------------------------------------------------------------------


class TestInplaceVar:
    def test_iadd(self):
        from mcp_google_workspace.sandbox import _inplacevar

        assert _inplacevar("+=", 5, 3) == 8

    def test_isub(self):
        from mcp_google_workspace.sandbox import _inplacevar

        assert _inplacevar("-=", 10, 4) == 6

    def test_imul(self):
        from mcp_google_workspace.sandbox import _inplacevar

        assert _inplacevar("*=", 3, 7) == 21

    def test_itruediv(self):
        from mcp_google_workspace.sandbox import _inplacevar

        assert _inplacevar("/=", 10, 4) == 2.5

    def test_ifloordiv(self):
        from mcp_google_workspace.sandbox import _inplacevar

        assert _inplacevar("//=", 10, 3) == 3

    def test_imod(self):
        from mcp_google_workspace.sandbox import _inplacevar

        assert _inplacevar("%=", 10, 3) == 1

    def test_ipow(self):
        from mcp_google_workspace.sandbox import _inplacevar

        assert _inplacevar("**=", 2, 10) == 1024

    def test_unsupported_op_raises(self):
        from mcp_google_workspace.sandbox import _inplacevar

        with pytest.raises(ValueError, match="Unsupported"):
            _inplacevar("??=", 1, 2)


# ---------------------------------------------------------------------------
# _build_help tests
# ---------------------------------------------------------------------------


class TestBuildHelp:
    def test_help_no_arg_lists_tools(self):
        from mcp_google_workspace.sandbox import _build_help

        metadata = {
            "tool_a": {"description": "Does A", "parameters": []},
            "tool_b": {"description": "Does B", "parameters": []},
        }
        h = _build_help(metadata)
        result = h()
        assert "tool_a" in result
        assert "tool_b" in result
        assert "Available tools" in result

    def test_help_specific_tool(self):
        from mcp_google_workspace.sandbox import _build_help

        metadata = {
            "my_tool": {
                "description": "A useful tool",
                "parameters": [
                    {"name": "x", "type": "string", "required": True, "description": "input"},
                ],
            },
        }
        h = _build_help(metadata)
        result = h("my_tool")
        assert "my_tool" in result
        assert "A useful tool" in result
        assert "x" in result

    def test_help_unknown_tool(self):
        from mcp_google_workspace.sandbox import _build_help

        h = _build_help({})
        result = h("nonexistent")
        assert "Unknown" in result

    def test_help_truncates_long_description(self):
        from mcp_google_workspace.sandbox import _build_help

        metadata = {
            "verbose_tool": {"description": "A" * 100, "parameters": []},
        }
        h = _build_help(metadata)
        result = h()
        # Description should be truncated at 80 chars
        assert "…" in result


# ---------------------------------------------------------------------------
# _ensure_serializable edge cases
# ---------------------------------------------------------------------------


class TestEnsureSerializableExtended:
    def test_large_repr_truncated(self):
        from mcp_google_workspace.sandbox import MAX_RESULT_BYTES, _ensure_serializable

        class BigRepr:
            def __repr__(self):
                return "X" * (MAX_RESULT_BYTES + 1000)

        result = _ensure_serializable(BigRepr())
        assert isinstance(result, str)
        assert "truncated" in result

    def test_list_passes(self):
        assert _ensure_serializable([1, 2, 3]) == [1, 2, 3]

    def test_string_passes(self):
        assert _ensure_serializable("hello") == "hello"

    def test_nested_dict_passes(self):
        d = {"a": {"b": [1, 2, {"c": True}]}}
        assert _ensure_serializable(d) == d


# ---------------------------------------------------------------------------
# Safe import guard
# ---------------------------------------------------------------------------


class TestSafeImport:
    def test_blocks_os(self):
        from mcp_google_workspace.sandbox import _safe_import

        with pytest.raises(ImportError, match="not allowed"):
            _safe_import("os")

    def test_blocks_subprocess(self):
        from mcp_google_workspace.sandbox import _safe_import

        with pytest.raises(ImportError, match="not allowed"):
            _safe_import("subprocess")

    def test_blocks_submodule_of_blocked(self):
        from mcp_google_workspace.sandbox import _safe_import

        with pytest.raises(ImportError, match="not allowed"):
            _safe_import("os.path")

    def test_allows_json(self):
        from mcp_google_workspace.sandbox import _safe_import

        mod = _safe_import("json")
        assert hasattr(mod, "dumps")

    def test_allows_math(self):
        from mcp_google_workspace.sandbox import _safe_import

        mod = _safe_import("math")
        assert hasattr(mod, "sqrt")

    def test_unknown_module_rejected(self):
        from mcp_google_workspace.sandbox import _safe_import

        with pytest.raises(ImportError, match="not available"):
            _safe_import("some_random_module_xyz")


# ---------------------------------------------------------------------------
# Execution: augmented assignment in sandbox
# ---------------------------------------------------------------------------


class TestAugmentedAssignment:
    def test_iadd_in_script(self):
        registry = ToolRegistry()
        code = "x = 10\nx += 5\nx"
        result = execute_script(code, registry, CTX, timeout=10)
        assert result.get("error") is None
        assert result["result"] == 15

    def test_imul_in_script(self):
        registry = ToolRegistry()
        code = "x = 3\nx *= 4\nx"
        result = execute_script(code, registry, CTX, timeout=10)
        assert result.get("error") is None
        assert result["result"] == 12


# ---------------------------------------------------------------------------
# Execution: list/dict comprehensions
# ---------------------------------------------------------------------------


class TestComprehensions:
    def test_list_comprehension(self):
        registry = ToolRegistry()
        code = "[x * 2 for x in range(5)]"
        result = execute_script(code, registry, CTX, timeout=10)
        assert result.get("error") is None
        assert result["result"] == [0, 2, 4, 6, 8]

    def test_dict_comprehension(self):
        registry = ToolRegistry()
        code = "{k: k**2 for k in range(4)}"
        result = execute_script(code, registry, CTX, timeout=10)
        assert result.get("error") is None
        assert result["result"] == {"0": 0, "1": 1, "2": 4, "3": 9} or result["result"] == {0: 0, 1: 1, 2: 4, 3: 9}


# ---------------------------------------------------------------------------
# Execution: exception handling in script
# ---------------------------------------------------------------------------


class TestExceptionHandling:
    def test_try_except_works(self):
        registry = ToolRegistry()
        code = "try:\n    x = 1 / 0\nexcept ZeroDivisionError:\n    x = 'caught'\nx"
        result = execute_script(code, registry, CTX, timeout=10)
        assert result.get("error") is None
        assert result["result"] == "caught"


# ---------------------------------------------------------------------------
# Execution: data processing patterns
# ---------------------------------------------------------------------------


class TestDataProcessing:
    def test_json_round_trip(self):
        registry = ToolRegistry()
        code = (
            "import json\n"
            "data = {'key': 'value', 'num': 42}\n"
            "s = json.dumps(data)\n"
            "parsed = json.loads(s)\n"
            "parsed"
        )
        result = execute_script(code, registry, CTX, timeout=10)
        assert result.get("error") is None
        assert result["result"]["key"] == "value"
        assert result["result"]["num"] == 42

    def test_collections_counter(self):
        registry = ToolRegistry()
        code = (
            "import collections\n"
            "c = collections.Counter(['a', 'b', 'a', 'c', 'a'])\n"
            "dict(c)"
        )
        result = execute_script(code, registry, CTX, timeout=10)
        assert result.get("error") is None
        assert result["result"]["a"] == 3

    def test_re_search(self):
        registry = ToolRegistry()
        code = (
            "import re\n"
            "m = re.search(r'(\\d+)', 'abc123def')\n"
            "m.group(1)"
        )
        result = execute_script(code, registry, CTX, timeout=10)
        assert result.get("error") is None
        assert result["result"] == "123"


# ---------------------------------------------------------------------------
# Execution: memory/timeout edge cases
# ---------------------------------------------------------------------------


class TestExecutionEdgeCases:
    def test_timeout_clamped_to_max(self):
        """Timeout above MAX_TIMEOUT_SECONDS should be clamped, not error."""
        registry = ToolRegistry()
        code = "'ok'"
        result = execute_script(code, registry, CTX, timeout=9999)
        assert result.get("error") is None
        assert result["result"] == "ok"

    def test_timeout_clamped_to_min(self):
        """Timeout below 1 should be clamped to 1."""
        registry = ToolRegistry()
        code = "'ok'"
        result = execute_script(code, registry, CTX, timeout=-5)
        assert result.get("error") is None

    def test_memory_limit_clamped(self):
        """Memory limit below minimum should be clamped."""
        registry = ToolRegistry()
        code = "'ok'"
        result = execute_script(code, registry, CTX, timeout=10, memory_limit_mb=1)
        assert result.get("error") is None
