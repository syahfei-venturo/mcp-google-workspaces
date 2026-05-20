"""Markdown export tool for Google Docs.

Provides:
- get_document_as_markdown: Export a doc as markdown

Limitations:
- Docs-to-Markdown export is lossy (some formatting details are lost)
"""

import logging
import re
from typing import Any, Dict, List, Optional

from googleapiclient.errors import HttpError
from mcp.server.fastmcp import Context

from ...registry import ToolParameter, ToolRegistry
from ._utils import validate_document_id

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ORDERED_GLYPH_TYPES = frozenset(
    {"DECIMAL", "ZERO_DECIMAL", "UPPER_ALPHA", "ALPHA", "UPPER_ROMAN", "ROMAN"}
)

_MONOSPACE_FONTS = frozenset(
    {
        "Courier New",
        "Consolas",
        "monospace",
        "Source Code Pro",
        "Roboto Mono",
        "Fira Code",
        "JetBrains Mono",
        "Ubuntu Mono",
        "Inconsolata",
    }
)

_SAFE_URL_SCHEMES = ("http://", "https://", "mailto:")


def _is_safe_url(url: str) -> bool:
    """Whitelist URL schemes to prevent javascript:, file://, data: injection."""
    if not url or not isinstance(url, str):
        return False
    stripped = url.strip().lower()
    return any(stripped.startswith(scheme) for scheme in _SAFE_URL_SCHEMES)


# ---------------------------------------------------------------------------
# Google Docs -> Markdown (export)
# ---------------------------------------------------------------------------


class _DocsExporter:
    """Converts a Google Docs document structure to markdown text."""

    def __init__(self, doc: Dict[str, Any]):
        self._doc = doc
        self._inline_objects = doc.get("inlineObjects", {})
        self._lists = doc.get("lists", {})

    def export(self) -> str:
        body = self._doc.get("body", {})
        content = body.get("content", [])
        parts: List[str] = []
        prev_list = False
        skipped_types: List[str] = []

        for elem in content:
            if "paragraph" in elem:
                para = elem["paragraph"]
                is_list = para.get("bullet") is not None
                if prev_list and not is_list:
                    parts.append("\n")
                parts.append(self._export_paragraph(para))
                prev_list = is_list
            elif "table" in elem:
                if prev_list:
                    parts.append("\n")
                    prev_list = False
                parts.append(self._export_table(elem["table"]))
                parts.append("\n")
            elif "sectionBreak" in elem:
                continue
            else:
                elem_keys = [k for k in elem if k not in ("startIndex", "endIndex")]
                if elem_keys:
                    skipped_types.extend(elem_keys)

        if skipped_types:
            logger.info(
                "Document export skipped %d unsupported element(s): %s",
                len(skipped_types),
                set(skipped_types),
            )

        result = "".join(parts)
        result = re.sub(r"\n{3,}", "\n\n", result)
        return result.strip() + "\n" if result.strip() else ""

    # -- paragraph ----------------------------------------------------------

    def _export_paragraph(self, para: Dict) -> str:
        style = para.get("paragraphStyle", {})
        named = style.get("namedStyleType", "NORMAL_TEXT")
        bullet = para.get("bullet")
        text = self._runs_to_md(para.get("elements", []))
        stripped = text.strip()

        if not stripped and not bullet:
            return "\n"

        # Heading
        if named.startswith("HEADING_"):
            try:
                level = int(named.split("_")[1])
            except (IndexError, ValueError):
                level = 1
            return f"{'#' * level} {stripped}\n\n"
        if named == "TITLE":
            return f"# {stripped}\n\n"
        if named == "SUBTITLE":
            return f"## {stripped}\n\n"

        # List item
        if bullet:
            prefix = self._bullet_prefix(bullet)
            indent = "  " * bullet.get("nestingLevel", 0)
            return f"{indent}{prefix} {stripped}\n"

        # Normal paragraph
        return f"{stripped}\n\n"

    def _runs_to_md(self, elements: List[Dict]) -> str:
        parts: List[str] = []
        for elem in elements:
            if "textRun" in elem:
                parts.append(self._format_run(elem["textRun"]))
            elif "inlineObjectElement" in elem:
                parts.append(self._format_inline_image(elem["inlineObjectElement"]))
        return "".join(parts)

    def _format_run(self, run: Dict) -> str:
        content = run.get("content", "")
        ts = run.get("textStyle", {})

        if content == "\n":
            return ""

        trailing = content.endswith("\n")
        if trailing:
            content = content[:-1]
        if not content:
            return ""

        font = ts.get("weightedFontFamily", {}).get("fontFamily", "")
        is_code = font in _MONOSPACE_FONTS
        is_bold = ts.get("bold", False)
        is_italic = ts.get("italic", False)
        is_strike = ts.get("strikethrough", False)
        link_url = ts.get("link", {}).get("url", "")

        out = content
        if is_code:
            out = f"`{out}`"
        else:
            if is_strike:
                out = f"~~{out}~~"
            if is_bold and is_italic:
                out = f"***{out}***"
            elif is_bold:
                out = f"**{out}**"
            elif is_italic:
                out = f"*{out}*"

        if link_url:
            out = f"[{out}]({link_url})"
        return out

    def _format_inline_image(self, elem: Dict) -> str:
        obj_id = elem.get("inlineObjectId", "")
        obj = self._inline_objects.get(obj_id, {})
        props = obj.get("inlineObjectProperties", {}).get("embeddedObject", {})
        uri = props.get("imageProperties", {}).get("sourceUri", "") or props.get(
            "imageProperties", {}
        ).get("contentUri", "")
        alt = props.get("title", props.get("description", "image"))
        if uri and _is_safe_url(uri):
            return f"![{alt}]({uri})"
        if uri:
            logger.warning("Unsafe image URI scheme excluded from export: %.100s", uri)
        return f"[image: {alt}]"

    # -- table --------------------------------------------------------------

    def _export_table(self, table: Dict) -> str:
        rows = table.get("tableRows", [])
        if not rows:
            return ""

        md_rows: List[List[str]] = []
        for row in rows:
            cells: List[str] = []
            for cell in row.get("tableCells", []):
                cell_parts: List[str] = []
                for c in cell.get("content", []):
                    para = c.get("paragraph", {})
                    elements = para.get("elements", [])
                    part = self._runs_to_md(elements).strip()
                    if part:
                        cell_parts.append(part)
                cells.append(" ".join(cell_parts))
            md_rows.append(cells)

        if not md_rows:
            return ""
        ncols = max(len(r) for r in md_rows)
        for r in md_rows:
            while len(r) < ncols:
                r.append("")

        lines = [
            "| " + " | ".join(md_rows[0]) + " |",
            "| " + " | ".join("---" for _ in range(ncols)) + " |",
        ]
        for r in md_rows[1:]:
            lines.append("| " + " | ".join(r) + " |")
        return "\n".join(lines) + "\n"

    # -- list helpers -------------------------------------------------------

    def _bullet_prefix(self, bullet: Dict) -> str:
        list_id = bullet.get("listId", "")
        nesting = bullet.get("nestingLevel", 0)
        list_def = self._lists.get(list_id, {})
        nesting_levels = list_def.get("listProperties", {}).get("nestingLevel", [])

        glyph_type = ""
        if isinstance(nesting_levels, list) and nesting < len(nesting_levels):
            glyph_type = nesting_levels[nesting].get("glyphType", "")
        elif isinstance(nesting_levels, dict):
            level_data = nesting_levels.get(str(nesting), {})
            glyph_type = level_data.get("glyphType", "")

        return "1." if glyph_type in _ORDERED_GLYPH_TYPES else "-"


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------


def get_document_as_markdown(
    document_id: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Export a Google Document as markdown text.

    Conversion is lossy: some formatting details may not survive
    the round-trip.
    """
    if err := validate_document_id(document_id):
        return err

    docs_service = ctx.request_context.lifespan_context.docs_service

    try:
        doc = docs_service.documents().get(documentId=document_id).execute()
    except HttpError as exc:
        logger.error("Google API error reading document %s: %s", document_id, exc)
        return {"error": "Google API error reading document"}
    except Exception as exc:
        logger.error("Failed to read document %s: %s", document_id, exc, exc_info=True)
        return {"error": "Failed to read document"}

    exporter = _DocsExporter(doc)
    markdown = exporter.export()

    return {
        "documentId": document_id,
        "title": doc.get("title", ""),
        "markdown": markdown,
        "length": len(markdown),
    }


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register(registry: ToolRegistry) -> None:
    """Register markdown tools in the registry."""
    registry.register(
        name="get_document_as_markdown",
        description=(
            "Export a Google Document as readable markdown text. "
            "RECOMMENDED: use this instead of get_document for "
            "human-readable content extraction. "
            "Converts headings, formatting, lists, tables, links, "
            "and images to markdown syntax. "
            "Note: conversion is lossy — some formatting details may be lost."
        ),
        parameters=[
            ToolParameter(
                "document_id",
                "string",
                "The ID of the document (from URL)",
            ),
        ],
        tags=[
            "docs", "read", "markdown", "md", "export", "text",
            "convert", "extract", "content", "download", "get",
        ],
        fn=get_document_as_markdown,
        read_only=True,
    )
