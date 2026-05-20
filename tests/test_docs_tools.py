"""Tests for Google Docs tool functions with mocked API services."""

from unittest.mock import MagicMock

from mcp_google_workspace.tools.docs.read import (
    get_document,
    get_tables,
    get_text,
    search_document,
)
from mcp_google_workspace.tools.docs.write import (
    delete_content,
    insert_text,
    replace_text,
    update_formatting,
)
from mcp_google_workspace.tools.docs.manage import (
    create_document,
    delete_document,
    list_documents,
    share_document,
)


def _mock_ctx(docs_service=None, drive_service=None, folder_id=None):
    """Build a mock Context with lifespan_context services."""
    ctx = MagicMock()
    lifespan = MagicMock()
    lifespan.docs_service = docs_service or MagicMock()
    lifespan.drive_service = drive_service or MagicMock()
    lifespan.folder_id = folder_id
    ctx.request_context.lifespan_context = lifespan
    return ctx


def _sample_doc(title="Test Doc", text="Hello World"):
    """Return a minimal Google Docs API document response."""
    return {
        "documentId": "doc123",
        "title": title,
        "revisionId": "rev1",
        "body": {
            "content": [
                {
                    "paragraph": {
                        "elements": [
                            {"textRun": {"content": text}},
                        ]
                    },
                    "startIndex": 1,
                    "endIndex": 1 + len(text),
                }
            ]
        },
        "headers": {},
        "footers": {},
        "documentStyle": {},
    }


# --- Read tests ---


class TestGetDocument:
    """Tests for get_document."""

    def test_returns_structure(self):
        svc = MagicMock()
        svc.documents().get().execute.return_value = _sample_doc()
        ctx = _mock_ctx(docs_service=svc)

        result = get_document("doc123", ctx=ctx)
        assert result["documentId"] == "doc123"
        assert result["title"] == "Test Doc"
        assert "body" in result


class TestGetText:
    """Tests for get_text."""

    def test_extracts_plain_text(self):
        svc = MagicMock()
        svc.documents().get().execute.return_value = _sample_doc(text="Hello World")
        ctx = _mock_ctx(docs_service=svc)

        result = get_text("doc123", ctx=ctx)
        assert result["text"] == "Hello World"
        assert result["length"] == 11


class TestGetTables:
    """Tests for get_tables."""

    def test_extracts_tables(self):
        doc = {
            "documentId": "doc123",
            "title": "Table Doc",
            "body": {
                "content": [
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
                                                                    "content": "A"
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
                                                                    "content": "B"
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
                                                                    "content": "C"
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
                                                                    "content": "D"
                                                                }
                                                            }
                                                        ]
                                                    }
                                                }
                                            ]
                                        },
                                    ]
                                },
                            ],
                        },
                        "startIndex": 1,
                        "endIndex": 50,
                    }
                ]
            },
        }
        svc = MagicMock()
        svc.documents().get().execute.return_value = doc
        ctx = _mock_ctx(docs_service=svc)

        result = get_tables("doc123", ctx=ctx)
        assert result["tableCount"] == 1
        assert result["tables"][0]["data"] == [["A", "B"], ["C", "D"]]

    def test_no_tables(self):
        svc = MagicMock()
        svc.documents().get().execute.return_value = _sample_doc()
        ctx = _mock_ctx(docs_service=svc)

        result = get_tables("doc123", ctx=ctx)
        assert result["tableCount"] == 0
        assert result["tables"] == []


class TestSearchDocument:
    """Tests for search_document."""

    def test_finds_matches(self):
        svc = MagicMock()
        svc.documents().get().execute.return_value = _sample_doc(
            text="Hello World Hello"
        )
        ctx = _mock_ctx(docs_service=svc)

        result = search_document("doc123", "Hello", ctx=ctx)
        assert result["matchCount"] == 2

    def test_case_insensitive(self):
        svc = MagicMock()
        svc.documents().get().execute.return_value = _sample_doc(text="Hello HELLO")
        ctx = _mock_ctx(docs_service=svc)

        result = search_document("doc123", "hello", case_sensitive=False, ctx=ctx)
        assert result["matchCount"] == 2

    def test_no_match(self):
        svc = MagicMock()
        svc.documents().get().execute.return_value = _sample_doc(text="Hello World")
        ctx = _mock_ctx(docs_service=svc)

        result = search_document("doc123", "xyz", ctx=ctx)
        assert result["matchCount"] == 0

    # --- match_type tests ---

    def test_match_type_exact(self):
        """exact: matches only standalone occurrences equal to query."""
        svc = MagicMock()
        # Words separated by spaces: "cat" exact should NOT match "category"
        svc.documents().get().execute.return_value = _sample_doc(
            text="The cat sat on the category mat"
        )
        ctx = _mock_ctx(docs_service=svc)

        result = search_document(
            "doc123", "cat", match_type="exact", ctx=ctx
        )
        # "cat" as whole word, not "category"
        assert result["matchCount"] == 1
        assert result["matches"][0]["match"] == "cat"

    def test_match_type_exact_case_insensitive(self):
        svc = MagicMock()
        svc.documents().get().execute.return_value = _sample_doc(
            text="The CAT sat on the mat"
        )
        ctx = _mock_ctx(docs_service=svc)

        result = search_document(
            "doc123", "cat", match_type="exact", case_sensitive=False, ctx=ctx
        )
        assert result["matchCount"] == 1
        assert result["matches"][0]["match"] == "CAT"

    def test_match_type_exact_case_sensitive(self):
        svc = MagicMock()
        svc.documents().get().execute.return_value = _sample_doc(
            text="The CAT sat and the cat ran"
        )
        ctx = _mock_ctx(docs_service=svc)

        result = search_document(
            "doc123", "cat", match_type="exact", case_sensitive=True, ctx=ctx
        )
        assert result["matchCount"] == 1
        assert result["matches"][0]["match"] == "cat"

    def test_match_type_regex(self):
        """regex: pattern matching across the full text."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = _sample_doc(
            text="Order ABC-123 and XYZ-456 are ready"
        )
        ctx = _mock_ctx(docs_service=svc)

        result = search_document(
            "doc123", r"[A-Z]+-\d+", match_type="regex", ctx=ctx
        )
        assert result["matchCount"] == 2
        assert result["matches"][0]["match"] == "ABC-123"
        assert result["matches"][1]["match"] == "XYZ-456"

    def test_match_type_regex_invalid(self):
        """Invalid regex returns error."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = _sample_doc(text="test")
        ctx = _mock_ctx(docs_service=svc)

        result = search_document(
            "doc123", "[invalid(", match_type="regex", ctx=ctx
        )
        assert "error" in result

    def test_match_type_starts_with(self):
        """starts_with: matches words that start with the query."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = _sample_doc(
            text="preview preorder repress expression"
        )
        ctx = _mock_ctx(docs_service=svc)

        result = search_document(
            "doc123", "pre", match_type="starts_with", ctx=ctx
        )
        # "preview", "preorder" start with "pre"; "repress", "expression" do not
        assert result["matchCount"] == 2

    def test_match_type_invalid(self):
        """Unknown match_type returns error."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = _sample_doc(text="test")
        ctx = _mock_ctx(docs_service=svc)

        result = search_document(
            "doc123", "test", match_type="fuzzy", ctx=ctx
        )
        assert "error" in result

    def test_empty_query_returns_error(self):
        """Empty query should return error without hitting API."""
        ctx = _mock_ctx()
        result = search_document("doc123", "", ctx=ctx)
        assert "error" in result

    def test_whitespace_only_query_returns_error(self):
        """Whitespace-only query should return error."""
        ctx = _mock_ctx()
        result = search_document("doc123", "   ", ctx=ctx)
        assert "error" in result

    def test_query_length_limit(self):
        """Query exceeding max length should return error."""
        ctx = _mock_ctx()
        result = search_document("doc123", "a" * 1001, ctx=ctx)
        assert "error" in result
        assert "1000" in result["error"]

    def test_query_at_max_length_accepted(self):
        """Query at exactly max length should be accepted."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = _sample_doc(text="test")
        ctx = _mock_ctx(docs_service=svc)

        result = search_document("doc123", "a" * 1000, ctx=ctx)
        assert "error" not in result

    def test_api_error_returns_error_dict(self):
        """API exception should return error dict via safe_get_document."""
        svc = MagicMock()
        svc.documents().get().execute.side_effect = Exception("API quota exceeded")
        ctx = _mock_ctx(docs_service=svc)

        result = search_document("doc123", "test", ctx=ctx)
        assert "error" in result
        assert "API quota exceeded" in result["error"]

    def test_context_does_not_cut_words(self):
        """Context should extend to word boundaries, not cut mid-word."""
        svc = MagicMock()
        # Build text where 50-char boundary falls mid-word "extraordinarily"
        words = "the quick brown fox jumps over the lazy dog and extraordinarily "
        text = words + "target rest of text here"
        svc.documents().get().execute.return_value = _sample_doc(text=text)
        ctx = _mock_ctx(docs_service=svc)

        result = search_document("doc123", "target", ctx=ctx)
        assert result["matchCount"] == 1
        context = result["matches"][0]["context"]
        # Context should start at a word boundary, not mid-"extraordinarily"
        first_word = context.split()[0]
        # The first word in context should be a complete word from the text
        assert first_word in text


# --- Write tests ---


class TestInsertText:
    """Tests for insert_text."""

    def test_inserts_at_index(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = {"replies": []}
        ctx = _mock_ctx(docs_service=svc)

        result = insert_text("doc123", "New text", index=5, ctx=ctx)
        assert result["documentId"] == "doc123"
        assert result["insertedAt"] == 5
        assert result["textLength"] == 8


class TestDeleteContent:
    """Tests for delete_content."""

    def test_deletes_range(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = {"replies": []}
        ctx = _mock_ctx(docs_service=svc)

        result = delete_content("doc123", 1, 10, ctx=ctx)
        assert result["deletedRange"] == {"startIndex": 1, "endIndex": 10}

    def test_invalid_range(self):
        ctx = _mock_ctx()
        result = delete_content("doc123", 10, 5, ctx=ctx)
        assert "error" in result


class TestReplaceText:
    """Tests for replace_text."""

    def test_replaces_all(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = {
            "replies": [{"replaceAllText": {"occurrencesChanged": 3}}]
        }
        ctx = _mock_ctx(docs_service=svc)

        result = replace_text("doc123", "old", "new", ctx=ctx)
        assert result["occurrencesChanged"] == 3


class TestUpdateFormatting:
    """Tests for update_formatting."""

    def test_applies_bold(self):
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = {"replies": []}
        ctx = _mock_ctx(docs_service=svc)

        result = update_formatting("doc123", 1, 10, bold=True, ctx=ctx)
        assert "bold" in result["appliedStyles"]

    def test_no_styles_error(self):
        ctx = _mock_ctx()
        result = update_formatting("doc123", 1, 10, ctx=ctx)
        assert "error" in result

    def test_invalid_range(self):
        ctx = _mock_ctx()
        result = update_formatting("doc123", 10, 5, bold=True, ctx=ctx)
        assert "error" in result


# --- Manage tests ---


class TestCreateDocument:
    """Tests for create_document."""

    def test_creates_with_title(self):
        drive = MagicMock()
        drive.files().create().execute.return_value = {
            "id": "new_doc_id",
            "name": "My Document",
            "parents": ["folder123"],
        }
        ctx = _mock_ctx(drive_service=drive)

        result = create_document("My Document", ctx=ctx)
        assert result["documentId"] == "new_doc_id"
        assert result["title"] == "My Document"


class TestDeleteDocument:
    """Tests for delete_document."""

    def test_trashes_document(self):
        drive = MagicMock()
        drive.files().update().execute.return_value = {}
        ctx = _mock_ctx(drive_service=drive)

        result = delete_document("doc123", ctx=ctx)
        assert result["status"] == "trashed"


class TestListDocuments:
    """Tests for list_documents."""

    def test_returns_documents(self):
        drive = MagicMock()
        drive.files().list().execute.return_value = {
            "files": [
                {
                    "id": "doc1",
                    "name": "Doc 1",
                    "createdTime": "2024-01-01",
                    "modifiedTime": "2024-06-01",
                    "owners": [{"emailAddress": "test@example.com"}],
                    "webViewLink": "https://docs.google.com/doc1",
                },
            ]
        }
        ctx = _mock_ctx(drive_service=drive)

        result = list_documents(ctx=ctx)
        assert len(result["items"]) == 1
        assert result["items"][0]["id"] == "doc1"


class TestShareDocument:
    """Tests for share_document."""

    def test_shares_with_user(self):
        drive = MagicMock()
        drive.permissions().create().execute.return_value = {"id": "perm123"}
        ctx = _mock_ctx(drive_service=drive)

        result = share_document(
            "doc123",
            [{"email_address": "user@example.com", "role": "writer"}],
            ctx=ctx,
        )
        assert len(result["successes"]) == 1
        assert result["successes"][0]["email_address"] == "user@example.com"

    def test_invalid_role(self):
        ctx = _mock_ctx()
        result = share_document(
            "doc123",
            [{"email_address": "user@example.com", "role": "admin"}],
            ctx=ctx,
        )
        assert len(result["failures"]) == 1

    def test_missing_email(self):
        ctx = _mock_ctx()
        result = share_document(
            "doc123",
            [{"role": "writer"}],
            ctx=ctx,
        )
        assert len(result["failures"]) == 1
