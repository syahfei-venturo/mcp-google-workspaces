"""Sandboxed Python script execution engine.

Runs user-provided Python code in a subprocess with RestrictedPython
for compile-time safety.  All registered Google Workspace tools are
available as callable functions.  Tool calls are dispatched to the
parent process via IPC pipe, where they execute with the real API
context.

Security layers (defense in depth):

1. **RestrictedPython AST restrictions** (compile-time)
   - Blocks dangerous imports (os, sys, subprocess, …)
   - Guards attribute access (no ``__dunder__`` access)
   - Restricts builtins (no exec, eval, open, …)
2. **Subprocess isolation** (runtime)
   - Separate process via ``multiprocessing`` "spawn"
   - Clean kill on timeout via SIGKILL
   - Memory limits via ``RLIMIT_AS`` (Linux)
3. **Output / result limits**
   - stdout capped at 1 MB
   - Result value size-checked before IPC
"""

from __future__ import annotations

import ast
import io
import json as _json
import logging
import multiprocessing
import operator
import sys
import time
import traceback
from typing import Any, Dict, List, Optional

from .utils import retry_on_api_error

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_TIMEOUT_SECONDS = 30
MAX_TIMEOUT_SECONDS = 300
DEFAULT_MEMORY_LIMIT_MB = 256
MAX_MEMORY_LIMIT_MB = 1024
MAX_OUTPUT_BYTES = 1_000_000  # 1 MB stdout capture
MAX_CODE_BYTES = 500_000  # 500 KB source code limit
MAX_RESULT_BYTES = 1_000_000  # 1 MB result value limit

# IPC message types
_MSG_TOOL_CALL = "tool_call"
_MSG_DONE = "done"
_MSG_ERROR = "error"

# Modules explicitly blocked inside the sandbox
BLOCKED_MODULES: frozenset = frozenset(
    {
        "os",
        "sys",
        "subprocess",
        "socket",
        "http",
        "urllib",
        "requests",
        "shutil",
        "pathlib",
        "signal",
        "ctypes",
        "multiprocessing",
        "threading",
        "asyncio",
        "importlib",
        "pickle",
        "shelve",
        "marshal",
        "code",
        "codeop",
        "compileall",
        "py_compile",
        "webbrowser",
        "antigravity",
        "turtle",
        "tempfile",
        "glob",
        "fnmatch",
        "resource",
        "pty",
        "fcntl",
        "termios",
        "mmap",
        "select",
        "selectors",
        "builtins",
        "gc",
        "inspect",
        "_thread",
        "concurrent",
    }
)

# Modules allowed for data-processing work inside the sandbox
ALLOWED_MODULES: frozenset = frozenset(
    {
        "json",
        "math",
        "datetime",
        "decimal",
        "fractions",
        "statistics",
        "collections",
        "itertools",
        "functools",
        "operator",
        "string",
        "re",
        "textwrap",
        "copy",
        "pprint",
        "enum",
        "dataclasses",
        "typing",
        "abc",
        "numbers",
        "csv",
        "io",
        "base64",
        "hashlib",
        "hmac",
        "uuid",
        "random",
        "time",
    }
)

# In-place operator dispatch table
_INPLACE_OPS: Dict[str, Any] = {
    "+=": operator.iadd,
    "-=": operator.isub,
    "*=": operator.imul,
    "/=": operator.itruediv,
    "//=": operator.ifloordiv,
    "%=": operator.imod,
    "**=": operator.ipow,
    "<<=": operator.ilshift,
    ">>=": operator.irshift,
    "&=": operator.iand,
    "^=": operator.ixor,
    "|=": operator.ior,
}


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _wrap_last_expression(source: str) -> str:
    """Capture the last statement's value into ``sandbox_result``.

    Handles two cases:
    - Bare expression: ``expr`` → ``sandbox_result = expr``
    - Simple assignment: ``x = expr`` → keeps assignment, appends
      ``sandbox_result = x`` so the assigned value is returned.

    Falls back to the original source on any parse error.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source

    if not tree.body:
        return source

    last = tree.body[-1]

    if isinstance(last, ast.Expr):
        # Bare expression → capture directly
        assign = ast.Assign(
            targets=[ast.Name(id="sandbox_result", ctx=ast.Store())],
            value=last.value,
        )
        ast.copy_location(assign, last)
        ast.fix_missing_locations(assign)
        tree.body[-1] = assign
    elif isinstance(last, ast.Assign) and len(last.targets) == 1:
        # Simple assignment (x = ...) → append sandbox_result = x
        target = last.targets[0]
        if isinstance(target, ast.Name):
            capture = ast.Assign(
                targets=[ast.Name(id="sandbox_result", ctx=ast.Store())],
                value=ast.Name(id=target.id, ctx=ast.Load()),
            )
            ast.copy_location(capture, last)
            ast.fix_missing_locations(capture)
            tree.body.append(capture)
    else:
        return source

    try:
        return ast.unparse(tree)
    except Exception:
        return source


# ---------------------------------------------------------------------------
# Import guard (runs inside the child process)
# ---------------------------------------------------------------------------


def _safe_import(
    name: str,
    globals: Any = None,
    locals: Any = None,
    fromlist: Any = (),
    level: int = 0,
) -> Any:
    """Import guard: only allow explicitly whitelisted modules."""
    top = name.split(".")[0]
    if top in BLOCKED_MODULES:
        raise ImportError(f"Module '{name}' is not allowed in sandbox")
    if top not in ALLOWED_MODULES:
        raise ImportError(
            f"Module '{name}' is not available in sandbox. "
            f"Allowed: {', '.join(sorted(ALLOWED_MODULES))}"
        )
    return __import__(name, globals, locals, fromlist, level)


# ---------------------------------------------------------------------------
# Stdout capture with size limits (runs inside the child process)
# ---------------------------------------------------------------------------


class _LimitedWriter:
    """Replacement for ``sys.stdout`` that enforces a size cap."""

    encoding = "utf-8"

    def __init__(self, max_bytes: int = MAX_OUTPUT_BYTES) -> None:
        self._parts: List[str] = []
        self._total: int = 0
        self._max: int = max_bytes
        self._truncated: bool = False

    def write(self, s: str) -> int:
        if self._truncated:
            return 0
        size = len(s)
        if self._total + size > self._max:
            remaining = self._max - self._total
            if remaining > 0:
                self._parts.append(s[:remaining])
            self._truncated = True
            return max(remaining, 0)
        self._parts.append(s)
        self._total += size
        return size

    def flush(self) -> None:
        pass

    def getvalue(self) -> str:
        return "".join(self._parts)

    @property
    def truncated(self) -> bool:
        return self._truncated

    def readable(self) -> bool:
        return False

    def writable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return False


# ---------------------------------------------------------------------------
# RestrictedPython guard helpers
# ---------------------------------------------------------------------------


def _inplacevar(op: str, x: Any, y: Any) -> Any:
    """Handle augmented assignments (``x += y``, ``x -= y``, etc.)."""
    fn = _INPLACE_OPS.get(op)
    if fn is None:
        raise ValueError(f"Unsupported in-place operator: {op}")
    return fn(x, y)


# ---------------------------------------------------------------------------
# Help function builder
# ---------------------------------------------------------------------------


def _build_help(tool_metadata: Dict[str, Any]):
    """Return a ``help()`` function for the sandbox namespace."""

    def help_fn(tool_name: str | None = None) -> str:
        if tool_name is None:
            names = sorted(tool_metadata.keys())
            lines = ["Available tools:", ""]
            for n in names:
                desc = tool_metadata[n].get("description", "")
                short = desc[:80] + "…" if len(desc) > 80 else desc
                lines.append(f"  {n:40s} {short}")
            lines.append("")
            lines.append("Call help('tool_name') for parameter details.")
            return "\n".join(lines)

        info = tool_metadata.get(tool_name)
        if info is None:
            return f"Unknown tool: '{tool_name}'"

        lines = [f"{tool_name}", f"  {info.get('description', '')}", "", "Parameters:"]
        for p in info.get("parameters", []):
            req = "required" if p.get("required", True) else "optional"
            lines.append(f"  {p['name']} ({p['type']}, {req}): {p.get('description', '')}")
        return "\n".join(lines)

    return help_fn


# ---------------------------------------------------------------------------
# Ensure a value is safe for IPC (pickle-serializable)
# ---------------------------------------------------------------------------


def _ensure_serializable(value: Any) -> Any:
    """Coerce *value* to something pickle- and JSON-safe."""
    try:
        _json.dumps(value)
        return value
    except (TypeError, ValueError, OverflowError):
        pass
    s = repr(value)
    if len(s) > MAX_RESULT_BYTES:
        return s[:MAX_RESULT_BYTES] + "…[truncated]"
    return s


# ---------------------------------------------------------------------------
# Child process entry point
# ---------------------------------------------------------------------------


def _child_worker(
    code_str: str,
    tool_names: List[str],
    tool_metadata: Dict[str, Any],
    conn: Any,
    memory_limit_bytes: int,
) -> None:
    """Execute a user script in the sandboxed child process.

    Tool calls are dispatched to the parent via *conn*.
    """
    # --- Resource limits (Linux only; no-op on macOS) ---
    try:
        import resource as _res

        _res.setrlimit(_res.RLIMIT_AS, (memory_limit_bytes, memory_limit_bytes))
    except (ImportError, ValueError, OSError):
        pass

    # --- Redirect stdout ---
    captured = _LimitedWriter(MAX_OUTPUT_BYTES)
    old_stdout = sys.stdout
    sys.stdout = captured  # type: ignore[assignment]

    try:
        # --- Import RestrictedPython ---
        try:
            from RestrictedPython import compile_restricted, safe_builtins
            from RestrictedPython.Guards import (
                guarded_unpack_sequence,
                safer_getattr,
            )
            from RestrictedPython.PrintCollector import PrintCollector
        except ImportError:
            conn.send(
                {
                    "type": _MSG_ERROR,
                    "error": "RestrictedPython is not installed",
                    "output": "",
                }
            )
            return

        # --- Compile restricted code ---
        try:
            byte_code = compile_restricted(code_str, filename="<sandbox>", mode="exec")
        except SyntaxError as exc:
            conn.send(
                {
                    "type": _MSG_ERROR,
                    "error": f"SyntaxError: {exc}",
                    "output": "",
                }
            )
            return

        if byte_code is None:
            conn.send(
                {
                    "type": _MSG_ERROR,
                    "error": "Code rejected by sandbox (RestrictedPython compilation failed)",
                    "output": "",
                }
            )
            return

        # --- Build tool proxy closures ---
        def _make_proxy(name: str):
            def proxy(**kwargs):  # noqa: ANN202
                try:
                    conn.send({"type": _MSG_TOOL_CALL, "name": name, "params": kwargs})
                    resp = conn.recv()
                except (EOFError, BrokenPipeError, ConnectionResetError):
                    raise RuntimeError("Lost connection to parent process") from None
                if resp.get("error"):
                    raise RuntimeError(f"Tool '{name}' error: {resp['error']}")
                return resp.get("result")

            proxy.__name__ = name
            proxy.__doc__ = tool_metadata.get(name, {}).get("description", "")
            return proxy

        # --- Build restricted builtins ---
        builtins = dict(safe_builtins)
        builtins["__import__"] = _safe_import
        builtins["_getattr_"] = safer_getattr
        builtins["_getitem_"] = lambda obj, key: obj[key]
        builtins["_getiter_"] = iter
        builtins["_write_"] = lambda obj: obj
        builtins["_inplacevar_"] = _inplacevar
        builtins["_unpack_sequence_"] = guarded_unpack_sequence
        builtins["_iter_unpack_sequence_"] = guarded_unpack_sequence
        builtins["_apply_"] = lambda func, *args, **kwargs: func(*args, **kwargs)

        # Ensure common builtins are present
        _extra_builtins = {
            "True": True,
            "False": False,
            "None": None,
            "bool": bool,
            "int": int,
            "float": float,
            "str": str,
            "bytes": bytes,
            "bytearray": bytearray,
            "complex": complex,
            "list": list,
            "dict": dict,
            "tuple": tuple,
            "set": set,
            "frozenset": frozenset,
            "type": type,
            "object": object,
            "abs": abs,
            "all": all,
            "any": any,
            "bin": bin,
            "chr": chr,
            "ord": ord,
            "hex": hex,
            "oct": oct,
            "divmod": divmod,
            "enumerate": enumerate,
            "filter": filter,
            "format": format,
            "hash": hash,
            "id": id,
            "isinstance": isinstance,
            "issubclass": issubclass,
            "iter": iter,
            "len": len,
            "map": map,
            "max": max,
            "min": min,
            "next": next,
            "pow": pow,
            "print": print,  # uses redirected stdout
            "range": range,
            "repr": repr,
            "reversed": reversed,
            "round": round,
            "slice": slice,
            "sorted": sorted,
            "sum": sum,
            "zip": zip,
            "hasattr": hasattr,
            # Exceptions
            "Exception": Exception,
            "TypeError": TypeError,
            "ValueError": ValueError,
            "KeyError": KeyError,
            "IndexError": IndexError,
            "AttributeError": AttributeError,
            "RuntimeError": RuntimeError,
            "StopIteration": StopIteration,
            "ZeroDivisionError": ZeroDivisionError,
            "NotImplementedError": NotImplementedError,
            "OverflowError": OverflowError,
            "ArithmeticError": ArithmeticError,
            "LookupError": LookupError,
            "ImportError": ImportError,
            "OSError": OSError,
        }
        for k, v in _extra_builtins.items():
            builtins.setdefault(k, v)

        # --- Build restricted globals ---
        restricted_globals: Dict[str, Any] = {
            "__builtins__": builtins,
            "__name__": "__sandbox__",
            "__metaclass__": type,
            "_getattr_": safer_getattr,
            "_getitem_": lambda obj, key: obj[key],
            "_getiter_": iter,
            "_write_": lambda obj: obj,
            "_inplacevar_": _inplacevar,
            "_print_": PrintCollector,
            "sandbox_result": None,
            "tools": sorted(tool_names),
            "help": _build_help(tool_metadata),
        }

        # Inject tool functions
        for name in tool_names:
            restricted_globals[name] = _make_proxy(name)

        # --- Execute ---
        exec(byte_code, restricted_globals)  # noqa: S102

        result_value = _ensure_serializable(restricted_globals.get("sandbox_result"))

        # Collect print output from PrintCollector (RestrictedPython
        # transforms print() → _print_()._call_print() and stores the
        # collector in the '_print' local).
        print_collector = restricted_globals.get("_print")
        if print_collector and callable(print_collector):
            printed_text = str(print_collector())
        elif print_collector and hasattr(print_collector, "txt"):
            printed_text = "".join(str(t) for t in print_collector.txt)
        else:
            printed_text = ""

        # Merge: PrintCollector output + any raw stdout writes
        raw_stdout = captured.getvalue()
        combined_output = printed_text + raw_stdout
        if len(combined_output) > MAX_OUTPUT_BYTES:
            combined_output = combined_output[:MAX_OUTPUT_BYTES]

        try:
            conn.send(
                {
                    "type": _MSG_DONE,
                    "output": combined_output,
                    "result": result_value,
                    "truncated": captured.truncated or len(combined_output) >= MAX_OUTPUT_BYTES,
                }
            )
        except Exception:
            conn.send(
                {
                    "type": _MSG_DONE,
                    "output": combined_output,
                    "result": str(result_value),
                    "truncated": captured.truncated,
                }
            )

    except MemoryError:
        _send_error(conn, captured, restricted_globals if "restricted_globals" in dir() else {},
                     "MemoryError: script exceeded memory limit")
    except Exception as exc:
        tb_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
        _send_error(conn, captured, restricted_globals if "restricted_globals" in dir() else {},
                     f"{type(exc).__name__}: {exc}", "".join(tb_lines))
    finally:
        sys.stdout = old_stdout


def _send_error(conn, captured, rg, error_msg, tb=None):
    """Helper to send error with combined output from PrintCollector + stdout."""
    pc = rg.get("_print") if isinstance(rg, dict) else None
    printed = ""
    if pc and callable(pc):
        try:
            printed = str(pc())
        except Exception:
            pass
    output = printed + captured.getvalue()
    msg = {"type": _MSG_ERROR, "error": error_msg, "output": output}
    if tb:
        msg["traceback"] = tb
    conn.send(msg)


# ---------------------------------------------------------------------------
# Parent-process orchestrator
# ---------------------------------------------------------------------------


def execute_script(
    code: str,
    registry: Any,
    ctx: Any,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    memory_limit_mb: int = DEFAULT_MEMORY_LIMIT_MB,
) -> Dict[str, Any]:
    """Execute a Python script in a sandboxed subprocess.

    All registered tools are available as callable functions in the
    script namespace.  Tool calls are dispatched back to *this*
    process for execution with the real Google API context.

    Args:
        code: Python source code to execute.
        registry: :class:`ToolRegistry` with all registered tools.
        ctx: MCP request context (forwarded to tool calls).
        timeout: Maximum execution time in seconds (1–300).
        memory_limit_mb: Memory limit in megabytes (64–1024).

    Returns:
        Dict with ``output``, ``result``, ``tool_calls``, and
        optionally ``error``, ``warning``, ``traceback``.
    """
    # --- Validate inputs ---
    if not code or not code.strip():
        return {"error": "Code must be a non-empty string"}

    code_bytes = len(code.encode("utf-8", errors="replace"))
    if code_bytes > MAX_CODE_BYTES:
        return {"error": f"Code exceeds maximum size ({MAX_CODE_BYTES:,} bytes)"}

    timeout = max(1, min(int(timeout), MAX_TIMEOUT_SECONDS))
    memory_limit_mb = max(64, min(int(memory_limit_mb), MAX_MEMORY_LIMIT_MB))
    memory_limit_bytes = memory_limit_mb * 1024 * 1024

    # --- Transform last expression for result capture ---
    transformed = _wrap_last_expression(code)

    # --- Build tool metadata for child process ---
    tool_names = registry.tool_names
    tool_metadata: Dict[str, Any] = {}
    for name in tool_names:
        tool = registry.get(name)
        if tool is not None:
            tool_metadata[name] = {
                "description": tool.description,
                "parameters": [
                    {
                        "name": p.name,
                        "type": p.type,
                        "required": p.required,
                        "description": p.description,
                    }
                    for p in tool.parameters
                ],
            }

    # --- Spawn child process ---
    mp_ctx = multiprocessing.get_context("spawn")
    parent_conn, child_conn = mp_ctx.Pipe()

    process = mp_ctx.Process(
        target=_child_worker,
        args=(transformed, tool_names, tool_metadata, child_conn, memory_limit_bytes),
        daemon=True,
    )

    tool_calls_log: List[Dict[str, Any]] = []
    output = ""

    try:
        process.start()
        child_conn.close()  # Parent doesn't use the child end

        deadline = time.monotonic() + timeout

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                process.kill()
                process.join(timeout=5)
                return {
                    "error": f"Script exceeded {timeout}s timeout",
                    "output": output,
                    "tool_calls": tool_calls_log,
                }

            if parent_conn.poll(timeout=min(remaining, 0.5)):
                try:
                    msg = parent_conn.recv()
                except (EOFError, ConnectionResetError, BrokenPipeError):
                    break

                msg_type = msg.get("type")

                if msg_type == _MSG_TOOL_CALL:
                    tool_name = msg["name"]
                    tool_params = msg.get("params", {})

                    tool = registry.get(tool_name)
                    if tool is None:
                        error_msg = (
                            f"Tool '{tool_name}' not found. "
                            "Use search_tools to discover tools."
                        )
                        tool_calls_log.append({"tool": tool_name, "error": error_msg})
                        parent_conn.send({"error": error_msg})
                    else:
                        try:
                            result = retry_on_api_error(tool.fn)(
                                **tool_params, ctx=ctx
                            )
                            tool_calls_log.append({
                                "tool": tool_name,
                                "result": _ensure_serializable(result),
                            })
                            parent_conn.send({"result": result})
                        except TypeError as exc:
                            error_msg = f"Invalid parameters for '{tool_name}': {exc}"
                            tool_calls_log.append({"tool": tool_name, "error": error_msg})
                            parent_conn.send({"error": error_msg})
                        except Exception as exc:
                            error_msg = f"Tool execution failed: {exc}"
                            tool_calls_log.append({"tool": tool_name, "error": error_msg})
                            parent_conn.send({"error": error_msg})

                elif msg_type == _MSG_DONE:
                    output = msg.get("output", "")
                    response: Dict[str, Any] = {
                        "output": output,
                        "result": msg.get("result"),
                        "tool_calls": tool_calls_log,
                    }
                    if msg.get("truncated"):
                        response["warning"] = "Output was truncated (exceeded 1 MB limit)"
                    return response

                elif msg_type == _MSG_ERROR:
                    output = msg.get("output", "")
                    response = {
                        "error": msg.get("error", "Unknown error"),
                        "output": output,
                        "tool_calls": tool_calls_log,
                    }
                    if msg.get("traceback"):
                        response["traceback"] = msg["traceback"]
                    return response

            # Check if child exited without sending a final message
            if not process.is_alive():
                exit_code = process.exitcode
                if exit_code == -9:
                    return {
                        "error": "Script killed (likely exceeded memory limit)",
                        "output": output,
                        "tool_calls": tool_calls_log,
                    }
                return {
                    "error": f"Script process exited unexpectedly (exit code: {exit_code})",
                    "output": output,
                    "tool_calls": tool_calls_log,
                }

    except Exception as exc:
        logger.error("Sandbox orchestration error: %s", exc, exc_info=True)
        return {
            "error": f"Sandbox error: {exc}",
            "output": output,
            "tool_calls": tool_calls_log,
        }

    finally:
        if process.is_alive():
            process.kill()
            process.join(timeout=5)
        parent_conn.close()

    # Should not reach here, but just in case
    return {
        "error": "Sandbox completed without producing a result",
        "output": output,
        "tool_calls": tool_calls_log,
    }
