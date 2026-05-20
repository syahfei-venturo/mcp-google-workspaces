"""Tests for Google Docs smart chip tools with mocked API services."""

from unittest.mock import MagicMock

from mcp_google_workspace.tools.docs.smart_chips import (
    insert_person_chip,
    insert_rich_link,
    list_smart_chips,
)


def _mock_ctx(docs_service=None):
    """Build a mock Context with lifespan_context services."""
    ctx = MagicMock()
    lifespan = MagicMock()
    lifespan.docs_service = docs_service or MagicMock()
    ctx.request_context.lifespan_context = lifespan
    return ctx


class TestInsertRichLink:
    """Tests for insert_rich_link."""

    def test_inserts_rich_link_successfully(self):
        """Happy path: insert a rich link at default position."""
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = {"replies": [{}]}
        ctx = _mock_ctx(docs_service=svc)

        result = insert_rich_link("doc1", uri="https://example.com", ctx=ctx)

        assert result["documentId"] == "doc1"
        assert result["uri"] == "https://example.com"
        assert result["insertedAt"] == 1

    def test_inserts_rich_link_at_custom_position(self):
        """Insert a rich link at a specific character index."""
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = {"replies": [{}]}
        ctx = _mock_ctx(docs_service=svc)

        result = insert_rich_link("doc1", uri="https://youtube.com/watch?v=abc", index=42, ctx=ctx)

        assert result["insertedAt"] == 42
        assert result["uri"] == "https://youtube.com/watch?v=abc"

    def test_inserts_drive_file_link(self):
        """Insert a Google Drive file as rich link."""
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = {"replies": [{}]}
        ctx = _mock_ctx(docs_service=svc)

        drive_url = "https://docs.google.com/spreadsheets/d/abc123/edit"
        result = insert_rich_link("doc1", uri=drive_url, ctx=ctx)

        assert result["uri"] == drive_url

    def test_empty_document_id(self):
        """Validation: empty document_id returns error."""
        ctx = _mock_ctx()
        result = insert_rich_link("", uri="https://example.com", ctx=ctx)
        assert "error" in result
        assert "document_id must be a non-empty string" in result["error"]

    def test_empty_uri(self):
        """Validation: empty URI returns error."""
        ctx = _mock_ctx()
        result = insert_rich_link("doc1", uri="", ctx=ctx)
        assert "error" in result
        assert "uri must be a non-empty string" in result["error"]

    def test_whitespace_only_uri(self):
        """Validation: whitespace-only URI returns error."""
        ctx = _mock_ctx()
        result = insert_rich_link("doc1", uri="   ", ctx=ctx)
        assert "error" in result

    def test_http_uri_rejected(self):
        """Validation: HTTP (non-HTTPS) URI is rejected."""
        ctx = _mock_ctx()
        result = insert_rich_link("doc1", uri="http://example.com", ctx=ctx)
        assert "error" in result
        assert "HTTPS" in result["error"]

    def test_non_url_rejected(self):
        """Validation: non-URL string is rejected."""
        ctx = _mock_ctx()
        result = insert_rich_link("doc1", uri="not a url", ctx=ctx)
        assert "error" in result

    def test_api_error_from_safe_batch_update(self):
        """API error from safe_batch_update is propagated."""
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = {
            "error": "Google API error: Invalid request"
        }
        ctx = _mock_ctx(docs_service=svc)

        result = insert_rich_link("doc1", uri="https://example.com", ctx=ctx)

        assert "error" in result


class TestInsertPersonChip:
    """Tests for insert_person_chip."""

    def test_inserts_person_chip_successfully(self):
        """Happy path: insert a person chip with valid email."""
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = {"replies": [{}]}
        ctx = _mock_ctx(docs_service=svc)

        result = insert_person_chip("doc1", email="user@domain.com", ctx=ctx)

        assert result["documentId"] == "doc1"
        assert result["email"] == "user@domain.com"
        assert result["type"] == "personChip"
        assert result["insertedAt"] == 1

    def test_inserts_person_chip_at_custom_position(self):
        """Insert a person chip at a specific character index."""
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = {"replies": [{}]}
        ctx = _mock_ctx(docs_service=svc)

        result = insert_person_chip("doc1", email="alice@example.org", index=100, ctx=ctx)

        assert result["insertedAt"] == 100
        assert result["email"] == "alice@example.org"

    def test_valid_email_formats(self):
        """Test various valid email formats."""
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = {"replies": [{}]}
        ctx = _mock_ctx(docs_service=svc)

        valid_emails = [
            "simple@example.com",
            "user.name@domain.com",
            "user+tag@example.co.uk",
            "first.last@company.org",
            "user_name@domain.io",
        ]

        for email in valid_emails:
            result = insert_person_chip("doc1", email=email, ctx=ctx)
            assert "error" not in result, f"Email {email} should be valid"
            assert result["email"] == email

    def test_invalid_email_empty_string(self):
        """Validation: empty email string is rejected."""
        ctx = _mock_ctx()
        result = insert_person_chip("doc1", email="", ctx=ctx)
        assert "error" in result
        assert "email must be a non-empty string" in result["error"]

    def test_invalid_email_whitespace_only(self):
        """Validation: whitespace-only email is rejected."""
        ctx = _mock_ctx()
        result = insert_person_chip("doc1", email="   ", ctx=ctx)
        assert "error" in result

    def test_invalid_email_no_at_sign(self):
        """Validation: email without @ sign is rejected."""
        ctx = _mock_ctx()
        result = insert_person_chip("doc1", email="notanemail", ctx=ctx)
        assert "error" in result
        assert "valid email address" in result["error"]

    def test_invalid_email_missing_domain(self):
        """Validation: email missing domain is rejected."""
        ctx = _mock_ctx()
        result = insert_person_chip("doc1", email="user@", ctx=ctx)
        assert "error" in result

    def test_invalid_email_missing_local(self):
        """Validation: email missing local part is rejected."""
        ctx = _mock_ctx()
        result = insert_person_chip("doc1", email="@domain.com", ctx=ctx)
        assert "error" in result

    def test_invalid_email_double_at(self):
        """Validation: email with multiple @ signs is rejected."""
        ctx = _mock_ctx()
        result = insert_person_chip("doc1", email="user@@domain.com", ctx=ctx)
        assert "error" in result

    def test_invalid_email_invalid_domain(self):
        """Validation: email with invalid domain is rejected."""
        ctx = _mock_ctx()
        result = insert_person_chip("doc1", email="user@.com", ctx=ctx)
        assert "error" in result

    def test_email_trimmed_before_use(self):
        """Email with surrounding whitespace is trimmed."""
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = {"replies": [{}]}
        ctx = _mock_ctx(docs_service=svc)

        result = insert_person_chip("doc1", email="  user@domain.com  ", ctx=ctx)

        assert result["email"] == "user@domain.com"

    def test_empty_document_id(self):
        """Validation: empty document_id returns error."""
        ctx = _mock_ctx()
        result = insert_person_chip("", email="user@domain.com", ctx=ctx)
        assert "error" in result
        assert "document_id must be a non-empty string" in result["error"]

    def test_api_error_from_safe_batch_update(self):
        """API error from safe_batch_update is propagated."""
        svc = MagicMock()
        svc.documents().batchUpdate().execute.return_value = {
            "error": "Google API error: Permission denied"
        }
        ctx = _mock_ctx(docs_service=svc)

        result = insert_person_chip("doc1", email="user@domain.com", ctx=ctx)

        assert "error" in result


class TestListSmartChips:
    """Tests for list_smart_chips."""

    def test_lists_rich_links_in_document(self):
        """Happy path: list rich links found in document."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = {
            "documentId": "doc1",
            "title": "Document with Links",
            "body": {
                "content": [
                    {
                        "paragraph": {
                            "elements": [
                                {
                                    "startIndex": 1,
                                    "endIndex": 2,
                                    "richLink": {
                                        "richLinkProperties": {
                                            "uri": "https://example.com",
                                            "title": "Example Website",
                                            "mimeType": "text/html",
                                        }
                                    },
                                }
                            ]
                        }
                    }
                ]
            },
        }
        ctx = _mock_ctx(docs_service=svc)

        result = list_smart_chips("doc1", ctx=ctx)

        assert result["documentId"] == "doc1"
        assert result["title"] == "Document with Links"
        assert result["count"] == 1
        assert len(result["smartChips"]) == 1
        chip = result["smartChips"][0]
        assert chip["uri"] == "https://example.com"
        assert chip["title"] == "Example Website"
        assert chip["mimeType"] == "text/html"

    def test_lists_multiple_rich_links(self):
        """Multiple rich links in the document."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = {
            "documentId": "doc1",
            "title": "Multi-Link Doc",
            "body": {
                "content": [
                    {
                        "paragraph": {
                            "elements": [
                                {
                                    "startIndex": 1,
                                    "endIndex": 2,
                                    "richLink": {
                                        "richLinkProperties": {
                                            "uri": "https://youtube.com/watch?v=abc",
                                            "title": "Video Title",
                                            "mimeType": "video/youtube",
                                        }
                                    },
                                },
                                {
                                    "startIndex": 50,
                                    "endIndex": 51,
                                    "richLink": {
                                        "richLinkProperties": {
                                            "uri": "https://drive.google.com/file/d/123/view",
                                            "title": "Shared File",
                                            "mimeType": "application/vnd.google-apps.spreadsheet",
                                        }
                                    },
                                },
                            ]
                        }
                    }
                ]
            },
        }
        ctx = _mock_ctx(docs_service=svc)

        result = list_smart_chips("doc1", ctx=ctx)

        assert result["count"] == 2
        assert len(result["smartChips"]) == 2
        assert result["smartChips"][0]["title"] == "Video Title"
        assert result["smartChips"][1]["title"] == "Shared File"

    def test_lists_person_chips(self):
        """Person chips (rich links with mailto:) are captured."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = {
            "documentId": "doc1",
            "title": "Doc with Mentions",
            "body": {
                "content": [
                    {
                        "paragraph": {
                            "elements": [
                                {
                                    "startIndex": 1,
                                    "endIndex": 2,
                                    "richLink": {
                                        "richLinkProperties": {
                                            "uri": "mailto:user@domain.com",
                                            "title": "User Name",
                                            "mimeType": "application/vnd.google-apps.person",
                                        }
                                    },
                                }
                            ]
                        }
                    }
                ]
            },
        }
        ctx = _mock_ctx(docs_service=svc)

        result = list_smart_chips("doc1", ctx=ctx)

        assert result["count"] == 1
        chip = result["smartChips"][0]
        assert chip["uri"] == "mailto:user@domain.com"
        assert chip["mimeType"] == "application/vnd.google-apps.person"

    def test_empty_document_no_chips(self):
        """Document with no smart chips returns empty list."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = {
            "documentId": "doc1",
            "title": "Plain Text",
            "body": {
                "content": [
                    {
                        "paragraph": {
                            "elements": [
                                {
                                    "startIndex": 1,
                                    "endIndex": 10,
                                    "textRun": {"content": "Plain text"},
                                }
                            ]
                        }
                    }
                ]
            },
        }
        ctx = _mock_ctx(docs_service=svc)

        result = list_smart_chips("doc1", ctx=ctx)

        assert result["count"] == 0
        assert result["smartChips"] == []

    def test_document_with_missing_body(self):
        """Document with no body key handles gracefully."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = {
            "documentId": "doc1",
            "title": "Empty Doc",
        }
        ctx = _mock_ctx(docs_service=svc)

        result = list_smart_chips("doc1", ctx=ctx)

        assert result["count"] == 0
        assert result["smartChips"] == []

    def test_empty_document_id(self):
        """Validation: empty document_id returns error."""
        ctx = _mock_ctx()
        result = list_smart_chips("", ctx=ctx)
        assert "error" in result
        assert "document_id must be a non-empty string" in result["error"]

    def test_document_with_no_content(self):
        """Document with missing content key is handled gracefully."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = {
            "documentId": "doc1",
            "title": "Empty Content",
            "body": {},
        }
        ctx = _mock_ctx(docs_service=svc)

        result = list_smart_chips("doc1", ctx=ctx)

        assert result["count"] == 0
        assert result["smartChips"] == []

    def test_multiple_paragraphs_with_chips(self):
        """Smart chips across multiple paragraphs are all found."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = {
            "documentId": "doc1",
            "title": "Multi-paragraph",
            "body": {
                "content": [
                    {
                        "paragraph": {
                            "elements": [
                                {
                                    "startIndex": 1,
                                    "endIndex": 2,
                                    "richLink": {
                                        "richLinkProperties": {
                                            "uri": "https://example1.com",
                                            "title": "Link 1",
                                        }
                                    },
                                }
                            ]
                        }
                    },
                    {
                        "paragraph": {
                            "elements": [
                                {
                                    "startIndex": 100,
                                    "endIndex": 101,
                                    "richLink": {
                                        "richLinkProperties": {
                                            "uri": "https://example2.com",
                                            "title": "Link 2",
                                        }
                                    },
                                }
                            ]
                        }
                    },
                ]
            },
        }
        ctx = _mock_ctx(docs_service=svc)

        result = list_smart_chips("doc1", ctx=ctx)

        assert result["count"] == 2
        assert result["smartChips"][0]["title"] == "Link 1"
        assert result["smartChips"][1]["title"] == "Link 2"

    def test_paragraph_without_elements(self):
        """Paragraph with no elements is skipped gracefully."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = {
            "documentId": "doc1",
            "title": "Mixed",
            "body": {
                "content": [
                    {"paragraph": {}},
                    {
                        "paragraph": {
                            "elements": [
                                {
                                    "startIndex": 1,
                                    "endIndex": 2,
                                    "richLink": {
                                        "richLinkProperties": {
                                            "uri": "https://example.com",
                                            "title": "Found Link",
                                        }
                                    },
                                }
                            ]
                        }
                    },
                ]
            },
        }
        ctx = _mock_ctx(docs_service=svc)

        result = list_smart_chips("doc1", ctx=ctx)

        assert result["count"] == 1
        assert result["smartChips"][0]["title"] == "Found Link"
