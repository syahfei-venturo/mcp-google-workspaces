"""Tests for Google Docs markdown export tool.

After removing markdown write tools, only the read/export path remains:
- _DocsExporter (Docs -> Markdown export)
- get_document_as_markdown tool function
- _is_safe_url security helper
"""

from unittest.mock import MagicMock

import pytest

from mcp_google_workspace.tools.docs.markdown import (
    _DocsExporter,
    _is_safe_url,
    get_document_as_markdown,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _mock_ctx(docs_service=None, drive_service=None, folder_id=None):
    """Build a mock Context with lifespan_context services."""
    ctx = MagicMock()
    lifespan = MagicMock()
    lifespan.docs_service = docs_service or MagicMock()
    lifespan.drive_service = drive_service or MagicMock()
    lifespan.folder_id = folder_id
    ctx.request_context.lifespan_context = lifespan
    return ctx


def _sample_doc(title="Test Doc", elements=None, lists=None, inline_objects=None):
    """Build a minimal Google Docs API document response."""
    if elements is None:
        elements = [
            {
                "paragraph": {
                    "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                    "elements": [{"textRun": {"content": "Hello\n", "textStyle": {}}}],
                },
                "startIndex": 1,
                "endIndex": 7,
            }
        ]
    return {
        "documentId": "doc123",
        "title": title,
        "body": {"content": elements},
        "lists": lists or {},
        "inlineObjects": inline_objects or {},
    }


# ===================================================================
# _DocsExporter unit tests
# ===================================================================


class TestDocsExporterHeadings:
    """Export headings to markdown # syntax."""

    @pytest.mark.parametrize("level", range(1, 7))
    def test_heading_export(self, level):
        doc = _sample_doc(
            elements=[
                {
                    "paragraph": {
                        "paragraphStyle": {"namedStyleType": f"HEADING_{level}"},
                        "elements": [
                            {"textRun": {"content": "My Heading\n", "textStyle": {}}}
                        ],
                    },
                    "startIndex": 1,
                    "endIndex": 12,
                }
            ]
        )
        exporter = _DocsExporter(doc)
        md = exporter.export()
        assert md.startswith("#" * level + " My Heading")

    def test_title_style(self):
        doc = _sample_doc(
            elements=[
                {
                    "paragraph": {
                        "paragraphStyle": {"namedStyleType": "TITLE"},
                        "elements": [
                            {"textRun": {"content": "Doc Title\n", "textStyle": {}}}
                        ],
                    },
                    "startIndex": 1,
                    "endIndex": 11,
                }
            ]
        )
        exporter = _DocsExporter(doc)
        md = exporter.export()
        assert md.startswith("# Doc Title")


class TestDocsExporterInlineFormatting:
    """Export bold, italic, strikethrough, code, links."""

    def test_bold(self):
        doc = _sample_doc(
            elements=[
                {
                    "paragraph": {
                        "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                        "elements": [
                            {"textRun": {"content": "This is ", "textStyle": {}}},
                            {
                                "textRun": {
                                    "content": "bold",
                                    "textStyle": {"bold": True},
                                }
                            },
                            {"textRun": {"content": "\n", "textStyle": {}}},
                        ],
                    },
                }
            ]
        )
        md = _DocsExporter(doc).export()
        assert "**bold**" in md

    def test_italic(self):
        doc = _sample_doc(
            elements=[
                {
                    "paragraph": {
                        "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                        "elements": [
                            {
                                "textRun": {
                                    "content": "italic",
                                    "textStyle": {"italic": True},
                                }
                            },
                            {"textRun": {"content": "\n", "textStyle": {}}},
                        ],
                    },
                }
            ]
        )
        md = _DocsExporter(doc).export()
        assert "*italic*" in md

    def test_strikethrough(self):
        doc = _sample_doc(
            elements=[
                {
                    "paragraph": {
                        "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                        "elements": [
                            {
                                "textRun": {
                                    "content": "deleted",
                                    "textStyle": {"strikethrough": True},
                                }
                            },
                            {"textRun": {"content": "\n", "textStyle": {}}},
                        ],
                    },
                }
            ]
        )
        md = _DocsExporter(doc).export()
        assert "~~deleted~~" in md

    def test_monospace_as_code(self):
        doc = _sample_doc(
            elements=[
                {
                    "paragraph": {
                        "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                        "elements": [
                            {
                                "textRun": {
                                    "content": "code",
                                    "textStyle": {
                                        "weightedFontFamily": {
                                            "fontFamily": "Courier New"
                                        }
                                    },
                                }
                            },
                            {"textRun": {"content": "\n", "textStyle": {}}},
                        ],
                    },
                }
            ]
        )
        md = _DocsExporter(doc).export()
        assert "`code`" in md

    def test_link(self):
        doc = _sample_doc(
            elements=[
                {
                    "paragraph": {
                        "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                        "elements": [
                            {
                                "textRun": {
                                    "content": "click",
                                    "textStyle": {
                                        "link": {"url": "https://example.com"}
                                    },
                                }
                            },
                            {"textRun": {"content": "\n", "textStyle": {}}},
                        ],
                    },
                }
            ]
        )
        md = _DocsExporter(doc).export()
        assert "[click](https://example.com)" in md

    def test_bold_italic_combined(self):
        doc = _sample_doc(
            elements=[
                {
                    "paragraph": {
                        "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                        "elements": [
                            {
                                "textRun": {
                                    "content": "both",
                                    "textStyle": {"bold": True, "italic": True},
                                }
                            },
                            {"textRun": {"content": "\n", "textStyle": {}}},
                        ],
                    },
                }
            ]
        )
        md = _DocsExporter(doc).export()
        assert "***both***" in md


class TestDocsExporterLists:
    """Export bullet and numbered lists."""

    def test_unordered_list(self):
        doc = _sample_doc(
            elements=[
                {
                    "paragraph": {
                        "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                        "bullet": {"listId": "L1", "nestingLevel": 0},
                        "elements": [
                            {"textRun": {"content": "Alpha\n", "textStyle": {}}}
                        ],
                    },
                },
                {
                    "paragraph": {
                        "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                        "bullet": {"listId": "L1", "nestingLevel": 0},
                        "elements": [
                            {"textRun": {"content": "Beta\n", "textStyle": {}}}
                        ],
                    },
                },
            ],
            lists={
                "L1": {
                    "listProperties": {
                        "nestingLevel": [{"glyphType": "GLYPH_TYPE_UNSPECIFIED"}],
                    }
                }
            },
        )
        md = _DocsExporter(doc).export()
        assert "- Alpha" in md
        assert "- Beta" in md

    def test_ordered_list(self):
        doc = _sample_doc(
            elements=[
                {
                    "paragraph": {
                        "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                        "bullet": {"listId": "L2", "nestingLevel": 0},
                        "elements": [
                            {"textRun": {"content": "First\n", "textStyle": {}}}
                        ],
                    },
                },
            ],
            lists={
                "L2": {
                    "listProperties": {
                        "nestingLevel": [{"glyphType": "DECIMAL"}],
                    }
                }
            },
        )
        md = _DocsExporter(doc).export()
        assert "1. First" in md

    def test_nested_list(self):
        doc = _sample_doc(
            elements=[
                {
                    "paragraph": {
                        "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                        "bullet": {"listId": "L1", "nestingLevel": 0},
                        "elements": [
                            {"textRun": {"content": "Top\n", "textStyle": {}}}
                        ],
                    },
                },
                {
                    "paragraph": {
                        "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                        "bullet": {"listId": "L1", "nestingLevel": 1},
                        "elements": [
                            {"textRun": {"content": "Nested\n", "textStyle": {}}}
                        ],
                    },
                },
            ],
            lists={
                "L1": {
                    "listProperties": {
                        "nestingLevel": [
                            {"glyphType": "GLYPH_TYPE_UNSPECIFIED"},
                            {"glyphType": "GLYPH_TYPE_UNSPECIFIED"},
                        ],
                    }
                }
            },
        )
        md = _DocsExporter(doc).export()
        assert "- Top" in md
        assert "  - Nested" in md


class TestDocsExporterTable:
    """Export tables to markdown pipe syntax."""

    def test_simple_table(self):
        doc = _sample_doc(
            elements=[
                {
                    "table": {
                        "rows": 2,
                        "columns": 2,
                        "tableRows": [
                            {
                                "tableCells": [
                                    {
                                        "content": [
                                            {
                                                "paragraph": {
                                                    "elements": [
                                                        {
                                                            "textRun": {
                                                                "content": "Name\n"
                                                            }
                                                        }
                                                    ]
                                                }
                                            }
                                        ]
                                    },
                                    {
                                        "content": [
                                            {
                                                "paragraph": {
                                                    "elements": [
                                                        {
                                                            "textRun": {
                                                                "content": "Age\n"
                                                            }
                                                        }
                                                    ]
                                                }
                                            }
                                        ]
                                    },
                                ]
                            },
                            {
                                "tableCells": [
                                    {
                                        "content": [
                                            {
                                                "paragraph": {
                                                    "elements": [
                                                        {
                                                            "textRun": {
                                                                "content": "Alice\n"
                                                            }
                                                        }
                                                    ]
                                                }
                                            }
                                        ]
                                    },
                                    {
                                        "content": [
                                            {
                                                "paragraph": {
                                                    "elements": [
                                                        {"textRun": {"content": "30\n"}}
                                                    ]
                                                }
                                            }
                                        ]
                                    },
                                ]
                            },
                        ],
                    },
                }
            ]
        )
        md = _DocsExporter(doc).export()
        assert "| Name | Age |" in md
        assert "| --- | --- |" in md
        assert "| Alice | 30 |" in md


class TestDocsExporterTableFormatting:
    """Export tables preserving cell formatting (bold, italic, code, links)."""

    def _cell(self, elements):
        """Helper to build a table cell with given paragraph elements."""
        return {"content": [{"paragraph": {"elements": elements}}]}

    def test_bold_in_cell(self):
        doc = _sample_doc(
            elements=[
                {
                    "table": {
                        "rows": 1,
                        "columns": 1,
                        "tableRows": [
                            {
                                "tableCells": [
                                    self._cell([
                                        {
                                            "textRun": {
                                                "content": "Header\n",
                                                "textStyle": {"bold": True},
                                            }
                                        }
                                    ]),
                                ]
                            },
                        ],
                    },
                }
            ]
        )
        md = _DocsExporter(doc).export()
        assert "**Header**" in md

    def test_link_in_cell(self):
        doc = _sample_doc(
            elements=[
                {
                    "table": {
                        "rows": 1,
                        "columns": 1,
                        "tableRows": [
                            {
                                "tableCells": [
                                    self._cell([
                                        {
                                            "textRun": {
                                                "content": "click\n",
                                                "textStyle": {
                                                    "link": {"url": "https://example.com"}
                                                },
                                            }
                                        }
                                    ]),
                                ]
                            },
                        ],
                    },
                }
            ]
        )
        md = _DocsExporter(doc).export()
        assert "[click](https://example.com)" in md


class TestDocsExporterEdgeCases:
    """Edge cases for document export."""

    def test_empty_document(self):
        doc = _sample_doc(elements=[])
        md = _DocsExporter(doc).export()
        assert md == ""

    def test_empty_paragraphs(self):
        doc = _sample_doc(
            elements=[
                {
                    "paragraph": {
                        "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                        "elements": [{"textRun": {"content": "\n", "textStyle": {}}}],
                    },
                }
            ]
        )
        md = _DocsExporter(doc).export()
        assert isinstance(md, str)

    def test_unknown_element_skipped(self):
        doc = _sample_doc(
            elements=[
                {
                    "paragraph": {
                        "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                        "elements": [
                            {"textRun": {"content": "Hello\n", "textStyle": {}}}
                        ],
                    },
                    "startIndex": 1,
                    "endIndex": 7,
                },
                {
                    "tableOfContents": {"content": []},
                    "startIndex": 7,
                    "endIndex": 20,
                },
            ]
        )
        md = _DocsExporter(doc).export()
        assert "Hello" in md
        assert "tableOfContents" not in md


# ===================================================================
# Tool function tests (with mocked API)
# ===================================================================


class TestGetDocumentAsMarkdown:
    """Test get_document_as_markdown tool function."""

    def test_validation_empty_id(self):
        result = get_document_as_markdown("", ctx=_mock_ctx())
        assert "error" in result

    def test_success(self):
        docs_svc = MagicMock()
        docs_svc.documents().get().execute.return_value = _sample_doc(
            title="Test",
            elements=[
                {
                    "paragraph": {
                        "paragraphStyle": {"namedStyleType": "HEADING_1"},
                        "elements": [
                            {"textRun": {"content": "Title\n", "textStyle": {}}}
                        ],
                    },
                }
            ],
        )

        ctx = _mock_ctx(docs_service=docs_svc)
        result = get_document_as_markdown("doc123", ctx=ctx)

        assert result["documentId"] == "doc123"
        assert "# Title" in result["markdown"]
        assert result["length"] > 0

    def test_api_failure(self):
        docs_svc = MagicMock()
        docs_svc.documents().get().execute.side_effect = Exception("Not found")

        ctx = _mock_ctx(docs_service=docs_svc)
        result = get_document_as_markdown("doc123", ctx=ctx)
        assert "error" in result


# ===================================================================
# Security: URL validation tests
# ===================================================================


class TestIsSafeUrl:
    """Unit tests for URL scheme validator."""

    def test_https(self):
        assert _is_safe_url("https://example.com") is True

    def test_http(self):
        assert _is_safe_url("http://example.com") is True

    def test_mailto(self):
        assert _is_safe_url("mailto:user@example.com") is True

    def test_javascript(self):
        assert _is_safe_url("javascript:alert(1)") is False

    def test_file(self):
        assert _is_safe_url("file:///etc/passwd") is False

    def test_data(self):
        assert _is_safe_url("data:text/plain;base64,SGVsbG8=") is False

    def test_ftp(self):
        assert _is_safe_url("ftp://example.com/file") is False

    def test_empty(self):
        assert _is_safe_url("") is False

    def test_none(self):
        assert _is_safe_url(None) is False

    def test_case_insensitive(self):
        assert _is_safe_url("HTTPS://EXAMPLE.COM") is True
        assert _is_safe_url("JAVASCRIPT:alert(1)") is False

    def test_whitespace_stripped(self):
        assert _is_safe_url("  https://example.com  ") is True


# ===================================================================
# Security: Image URI validation on export
# ===================================================================


class TestImageURIValidation:
    """Exported image URIs must use safe schemes only."""

    def test_https_image_exported(self):
        doc = _sample_doc(
            elements=[
                {
                    "paragraph": {
                        "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                        "elements": [
                            {"inlineObjectElement": {"inlineObjectId": "img1"}},
                            {"textRun": {"content": "\n", "textStyle": {}}},
                        ],
                    },
                }
            ],
            inline_objects={
                "img1": {
                    "inlineObjectProperties": {
                        "embeddedObject": {
                            "imageProperties": {
                                "sourceUri": "https://example.com/img.png"
                            },
                            "title": "photo",
                        }
                    }
                }
            },
        )
        md = _DocsExporter(doc).export()
        assert "![photo](https://example.com/img.png)" in md

    def test_file_uri_excluded(self):
        doc = _sample_doc(
            elements=[
                {
                    "paragraph": {
                        "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                        "elements": [
                            {"inlineObjectElement": {"inlineObjectId": "img1"}},
                            {"textRun": {"content": "\n", "textStyle": {}}},
                        ],
                    },
                }
            ],
            inline_objects={
                "img1": {
                    "inlineObjectProperties": {
                        "embeddedObject": {
                            "imageProperties": {"sourceUri": "file:///etc/passwd"},
                            "title": "secret",
                        }
                    }
                }
            },
        )
        md = _DocsExporter(doc).export()
        assert "file://" not in md
        assert "[image: secret]" in md
