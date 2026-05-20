"""Tests for Google Docs tab management tools with mocked API services."""

from unittest.mock import MagicMock

from mcp_google_workspace.tools.docs.tabs import (
    add_tab,
    list_document_tabs,
    rename_tab,
)


def _mock_ctx(docs_service=None):
    """Build a mock Context with lifespan_context services."""
    ctx = MagicMock()
    lifespan = MagicMock()
    lifespan.docs_service = docs_service or MagicMock()
    ctx.request_context.lifespan_context = lifespan
    return ctx


class TestListDocumentTabs:
    """Tests for list_document_tabs."""

    def test_lists_single_default_tab(self):
        """Happy path: document with default tab."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = {
            "documentId": "doc1",
            "title": "My Document",
            "tabs": [
                {
                    "tabProperties": {
                        "tabId": "default",
                        "title": "Default",
                        "index": 0,
                        "nestingLevel": 0,
                    }
                }
            ],
        }
        ctx = _mock_ctx(docs_service=svc)

        result = list_document_tabs("doc1", ctx=ctx)

        assert result["documentId"] == "doc1"
        assert result["title"] == "My Document"
        assert result["tabCount"] == 1
        assert len(result["tabs"]) == 1
        assert result["tabs"][0]["tabId"] == "default"
        assert result["tabs"][0]["title"] == "Default"
        assert result["tabs"][0]["nestingLevel"] == 0

    def test_lists_multiple_tabs(self):
        """Multiple tabs with varying nesting levels."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = {
            "documentId": "doc1",
            "title": "Multi-Tab Doc",
            "tabs": [
                {
                    "tabProperties": {
                        "tabId": "tab1",
                        "title": "Overview",
                        "index": 0,
                        "nestingLevel": 0,
                    }
                },
                {
                    "tabProperties": {
                        "tabId": "tab2",
                        "title": "Details",
                        "index": 1,
                        "nestingLevel": 0,
                    }
                },
                {
                    "tabProperties": {
                        "tabId": "tab3",
                        "title": "Sub-tab",
                        "index": 0,
                        "nestingLevel": 1,
                    }
                },
            ],
        }
        ctx = _mock_ctx(docs_service=svc)

        result = list_document_tabs("doc1", ctx=ctx)

        assert result["tabCount"] == 3
        assert len(result["tabs"]) == 3
        assert result["tabs"][0]["title"] == "Overview"
        assert result["tabs"][1]["title"] == "Details"
        assert result["tabs"][2]["title"] == "Sub-tab"
        assert result["tabs"][2]["nestingLevel"] == 1

    def test_empty_document_id(self):
        """Validation: empty document_id returns error."""
        ctx = _mock_ctx()
        result = list_document_tabs("", ctx=ctx)
        assert "error" in result
        assert "document_id must be a non-empty string" in result["error"]

    def test_whitespace_only_document_id(self):
        """Validation: whitespace-only document_id returns error."""
        ctx = _mock_ctx()
        result = list_document_tabs("   ", ctx=ctx)
        assert "error" in result

    def test_document_with_no_tabs_key(self):
        """Edge case: document structure without 'tabs' key defaults to empty."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = {
            "documentId": "doc1",
            "title": "No Tabs Doc",
        }
        ctx = _mock_ctx(docs_service=svc)

        result = list_document_tabs("doc1", ctx=ctx)

        assert result["tabCount"] == 0
        assert result["tabs"] == []

    def test_document_without_title(self):
        """Document without title key is handled gracefully."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = {
            "documentId": "doc1",
            "tabs": [
                {
                    "tabProperties": {
                        "tabId": "tab1",
                        "title": "Tab 1",
                        "index": 0,
                    }
                }
            ],
        }
        ctx = _mock_ctx(docs_service=svc)

        result = list_document_tabs("doc1", ctx=ctx)

        assert result["documentId"] == "doc1"
        assert result.get("title") is None
        assert result["tabCount"] == 1


class TestAddTab:
    """Tests for add_tab."""

    def test_adds_tab_with_title(self):
        """Happy path: add a new tab with a title."""
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = {
            "replies": [
                {
                    "createTab": {
                        "tabProperties": {
                            "tabId": "new-tab-123",
                            "title": "New Section",
                            "index": 1,
                            "nestingLevel": 0,
                        }
                    }
                }
            ]
        }
        ctx = _mock_ctx(docs_service=svc)

        result = add_tab("doc1", title="New Section", ctx=ctx)

        assert result["documentId"] == "doc1"
        assert result["tabId"] == "new-tab-123"
        assert result["title"] == "New Section"
        assert result["index"] == 1
        assert result["nestingLevel"] == 0

    def test_adds_tab_without_title(self):
        """Add tab without explicit title — defaults to system-generated."""
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = {
            "replies": [
                {
                    "createTab": {
                        "tabProperties": {
                            "tabId": "new-tab-456",
                            "title": "Tab 2",
                            "index": 1,
                            "nestingLevel": 0,
                        }
                    }
                }
            ]
        }
        ctx = _mock_ctx(docs_service=svc)

        result = add_tab("doc1", ctx=ctx)

        assert result["documentId"] == "doc1"
        assert result["tabId"] == "new-tab-456"
        assert "title" in result

    def test_adds_nested_child_tab(self):
        """Add a tab as a child of an existing parent tab."""
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = {
            "replies": [
                {
                    "createTab": {
                        "tabProperties": {
                            "tabId": "child-tab",
                            "title": "Child",
                            "index": 0,
                            "nestingLevel": 1,
                        }
                    }
                }
            ]
        }
        ctx = _mock_ctx(docs_service=svc)

        result = add_tab("doc1", title="Child", parent_tab_id="parent-tab", ctx=ctx)

        assert result["tabId"] == "child-tab"
        assert result["nestingLevel"] == 1

    def test_empty_document_id(self):
        """Validation: empty document_id returns error."""
        ctx = _mock_ctx()
        result = add_tab("", title="New Tab", ctx=ctx)
        assert "error" in result

    def test_api_error_from_safe_batch_update(self):
        """API error is propagated from safe_batch_update."""
        svc = MagicMock()
        svc.documents().batchUpdate().execute.side_effect = Exception("Rate limited")
        ctx = _mock_ctx(docs_service=svc)

        result = add_tab("doc1", title="New Tab", ctx=ctx)

        assert "error" in result

    def test_empty_reply_structure(self):
        """Handle empty replies gracefully."""
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = {"replies": []}
        ctx = _mock_ctx(docs_service=svc)

        result = add_tab("doc1", title="New Tab", ctx=ctx)

        assert result["documentId"] == "doc1"
        assert result["title"] == "New Tab"  # Falls back to input title


class TestRenameTab:
    """Tests for rename_tab."""

    def test_renames_tab_successfully(self):
        """Happy path: rename a tab."""
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = {"replies": [{}]}
        ctx = _mock_ctx(docs_service=svc)

        result = rename_tab("doc1", tab_id="tab-123", title="Updated Title", ctx=ctx)

        assert result["documentId"] == "doc1"
        assert result["tabId"] == "tab-123"
        assert result["title"] == "Updated Title"

    def test_empty_document_id(self):
        """Validation: empty document_id returns error."""
        ctx = _mock_ctx()
        result = rename_tab("", tab_id="tab-123", title="New Title", ctx=ctx)
        assert "error" in result
        assert "document_id must be a non-empty string" in result["error"]

    def test_empty_tab_id(self):
        """Validation: empty tab_id returns error."""
        ctx = _mock_ctx()
        result = rename_tab("doc1", tab_id="", title="New Title", ctx=ctx)
        assert "error" in result
        assert "tab_id must be a non-empty string" in result["error"]

    def test_whitespace_only_tab_id(self):
        """Validation: whitespace-only tab_id returns error."""
        ctx = _mock_ctx()
        result = rename_tab("doc1", tab_id="   ", title="New Title", ctx=ctx)
        assert "error" in result

    def test_empty_title(self):
        """Validation: empty title returns error."""
        ctx = _mock_ctx()
        result = rename_tab("doc1", tab_id="tab-123", title="", ctx=ctx)
        assert "error" in result
        assert "title must be a non-empty string" in result["error"]

    def test_whitespace_only_title(self):
        """Validation: whitespace-only title returns error."""
        ctx = _mock_ctx()
        result = rename_tab("doc1", tab_id="tab-123", title="   ", ctx=ctx)
        assert "error" in result

    def test_api_error_from_safe_batch_update(self):
        """API error from safe_batch_update is propagated."""
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = {
            "error": "Google API error: Document not found"
        }
        ctx = _mock_ctx(docs_service=svc)

        result = rename_tab("doc1", tab_id="tab-123", title="New Title", ctx=ctx)

        assert "error" in result
