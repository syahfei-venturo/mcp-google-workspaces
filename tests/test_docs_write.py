"""Tests for replace_first_text and replace_text_in_range."""

from unittest.mock import MagicMock, call

from mcp_google_workspace.tools.docs.write import (
    replace_first_text,
    replace_text_in_range,
)


def _mock_ctx(docs_service=None):
    """Build a mock Context with lifespan_context services."""
    ctx = MagicMock()
    lifespan = MagicMock()
    lifespan.docs_service = docs_service or MagicMock()
    ctx.request_context.lifespan_context = lifespan
    return ctx


def _sample_doc(text="Hello World", doc_id="doc123", title="Test Doc"):
    """Return a minimal Google Docs API document response.

    Simulates a document where body content starts at index 1.
    """
    return {
        "documentId": doc_id,
        "title": title,
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
    }


# ---------------------------------------------------------------------------
# replace_first_text — validation
# ---------------------------------------------------------------------------


class TestReplaceFirstTextValidation:
    """Input validation for replace_first_text."""

    def test_empty_document_id(self):
        result = replace_first_text("", "old", "new", ctx=_mock_ctx())
        assert "error" in result

    def test_empty_find_text(self):
        result = replace_first_text("doc123", "", "new", ctx=_mock_ctx())
        assert "error" in result

    def test_whitespace_find_text(self):
        result = replace_first_text("doc123", "   ", "new", ctx=_mock_ctx())
        assert "error" in result


# ---------------------------------------------------------------------------
# replace_first_text — success cases
# ---------------------------------------------------------------------------


class TestReplaceFirstTextSuccess:
    """Successful replace_first_text operations."""

    def test_replaces_only_first_occurrence(self):
        """When text appears multiple times, only the first is replaced."""
        svc = MagicMock()
        # "foo bar foo baz foo" — three occurrences of "foo"
        svc.documents().get().execute.return_value = _sample_doc(
            text="foo bar foo baz foo"
        )
        svc.documents().batchUpdate().execute.return_value = {"replies": [{}, {}]}
        ctx = _mock_ctx(docs_service=svc)

        result = replace_first_text("doc123", "foo", "replaced", ctx=ctx)

        assert "error" not in result
        assert result["documentId"] == "doc123"
        assert result["replacedAt"] == 1  # first "foo" starts at index 1

        # Verify batchUpdate was called with delete + insert
        batch_call = svc.documents().batchUpdate.call_args
        requests = batch_call[1]["body"]["requests"]
        assert len(requests) == 2
        # First request: delete the found text
        assert "deleteContentRange" in requests[0]
        delete_range = requests[0]["deleteContentRange"]["range"]
        assert delete_range["startIndex"] == 1
        assert delete_range["endIndex"] == 4  # "foo" is 3 chars, 1+3=4
        # Second request: insert replacement
        assert "insertText" in requests[1]
        assert requests[1]["insertText"]["text"] == "replaced"
        assert requests[1]["insertText"]["location"]["index"] == 1

    def test_case_insensitive_match(self):
        """Case-insensitive matching finds the first occurrence."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = _sample_doc(
            text="Hello HELLO hello"
        )
        svc.documents().batchUpdate().execute.return_value = {"replies": [{}, {}]}
        ctx = _mock_ctx(docs_service=svc)

        result = replace_first_text(
            "doc123", "hello", "hi", match_case=False, ctx=ctx
        )

        assert "error" not in result
        assert result["replacedAt"] == 1  # "Hello" at position 1

    def test_case_sensitive_match(self):
        """Case-sensitive matching skips non-matching case."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = _sample_doc(
            text="Hello HELLO hello"
        )
        svc.documents().batchUpdate().execute.return_value = {"replies": [{}, {}]}
        ctx = _mock_ctx(docs_service=svc)

        result = replace_first_text(
            "doc123", "HELLO", "hi", match_case=True, ctx=ctx
        )

        assert "error" not in result
        # "HELLO" starts at index 7 (1 + len("Hello ") = 7)
        assert result["replacedAt"] == 7

    def test_replace_with_empty_string(self):
        """Replacing with empty string effectively deletes the text."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = _sample_doc(text="remove_me rest")
        svc.documents().batchUpdate().execute.return_value = {"replies": [{}]}
        ctx = _mock_ctx(docs_service=svc)

        result = replace_first_text("doc123", "remove_me", "", ctx=ctx)

        assert "error" not in result
        # When replacement is empty, only delete is needed (no insert)
        batch_call = svc.documents().batchUpdate.call_args
        requests = batch_call[1]["body"]["requests"]
        assert len(requests) == 1
        assert "deleteContentRange" in requests[0]

    def test_single_batch_update_call(self):
        """All operations must be in a single atomic batchUpdate call."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = _sample_doc(text="old text here")
        svc.documents().batchUpdate().execute.return_value = {"replies": [{}, {}]}
        ctx = _mock_ctx(docs_service=svc)

        replace_first_text("doc123", "old", "new", ctx=ctx)

        # Filter real batchUpdate calls (those with keyword args, not setup calls)
        batch_calls = [
            c for c in svc.documents().batchUpdate.call_args_list
            if c[1]  # has keyword arguments
        ]
        assert len(batch_calls) == 1


# ---------------------------------------------------------------------------
# replace_first_text — no match / edge cases
# ---------------------------------------------------------------------------


class TestReplaceFirstTextEdgeCases:
    """Edge cases for replace_first_text."""

    def test_no_match_returns_zero(self):
        """When text is not found, return informative result without error."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = _sample_doc(text="Hello World")
        ctx = _mock_ctx(docs_service=svc)

        result = replace_first_text("doc123", "xyz", "new", ctx=ctx)

        assert "error" not in result
        assert result["occurrencesFound"] == 0
        # batchUpdate should NOT be called when there's nothing to replace
        svc.documents().batchUpdate.assert_not_called()

    def test_multi_paragraph_finds_first(self):
        """Works across paragraphs — finds the first occurrence overall."""
        doc = {
            "documentId": "doc123",
            "title": "Test",
            "body": {
                "content": [
                    {
                        "paragraph": {
                            "elements": [
                                {"textRun": {"content": "First paragraph\n"}},
                            ]
                        },
                        "startIndex": 1,
                        "endIndex": 17,
                    },
                    {
                        "paragraph": {
                            "elements": [
                                {"textRun": {"content": "target in second\n"}},
                            ]
                        },
                        "startIndex": 17,
                        "endIndex": 34,
                    },
                ]
            },
        }
        svc = MagicMock()
        svc.documents().get().execute.return_value = doc
        svc.documents().batchUpdate().execute.return_value = {"replies": [{}, {}]}
        ctx = _mock_ctx(docs_service=svc)

        result = replace_first_text("doc123", "target", "REPLACED", ctx=ctx)

        assert "error" not in result
        # "target" starts at "First paragraph\n" (16 chars) + 1 (base) = 17
        assert result["replacedAt"] == 17


# ---------------------------------------------------------------------------
# replace_text_in_range — validation
# ---------------------------------------------------------------------------


class TestReplaceTextInRangeValidation:
    """Input validation for replace_text_in_range."""

    def test_empty_document_id(self):
        result = replace_text_in_range("", "old", "new", 1, 100, ctx=_mock_ctx())
        assert "error" in result

    def test_empty_find_text(self):
        result = replace_text_in_range("doc123", "", "new", 1, 100, ctx=_mock_ctx())
        assert "error" in result

    def test_invalid_range_start_gte_end(self):
        result = replace_text_in_range(
            "doc123", "old", "new", 100, 50, ctx=_mock_ctx()
        )
        assert "error" in result

    def test_negative_start_index(self):
        result = replace_text_in_range(
            "doc123", "old", "new", -1, 50, ctx=_mock_ctx()
        )
        assert "error" in result


# ---------------------------------------------------------------------------
# replace_text_in_range — success cases
# ---------------------------------------------------------------------------


class TestReplaceTextInRangeSuccess:
    """Successful replace_text_in_range operations."""

    def test_replaces_all_in_range(self):
        """Replaces all occurrences within the given index range."""
        svc = MagicMock()
        # "foo bar foo baz foo" — 3x "foo", indices 1-20
        svc.documents().get().execute.return_value = _sample_doc(
            text="foo bar foo baz foo"
        )
        svc.documents().batchUpdate().execute.return_value = {"replies": [{}, {}]}
        ctx = _mock_ctx(docs_service=svc)

        # Range 1..12 covers "foo bar foo" — should find 2 occurrences
        result = replace_text_in_range(
            "doc123", "foo", "X", start_index=1, end_index=12, ctx=ctx
        )

        assert "error" not in result
        assert result["occurrencesReplaced"] == 2

    def test_ignores_matches_outside_range(self):
        """Matches outside the specified range are not replaced."""
        svc = MagicMock()
        # "foo bar foo baz foo" — indices: foo@1, foo@9, foo@17
        svc.documents().get().execute.return_value = _sample_doc(
            text="foo bar foo baz foo"
        )
        svc.documents().batchUpdate().execute.return_value = {"replies": [{}, {}]}
        ctx = _mock_ctx(docs_service=svc)

        # Range 8..16 covers " foo baz" — should find only 1 "foo" at index 9
        result = replace_text_in_range(
            "doc123", "foo", "X", start_index=8, end_index=16, ctx=ctx
        )

        assert "error" not in result
        assert result["occurrencesReplaced"] == 1

    def test_case_insensitive_in_range(self):
        """Case-insensitive matching within range."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = _sample_doc(
            text="Hello HELLO hello"
        )
        svc.documents().batchUpdate().execute.return_value = {"replies": [{}, {}]}
        ctx = _mock_ctx(docs_service=svc)

        result = replace_text_in_range(
            "doc123", "hello", "hi",
            start_index=1, end_index=18,
            match_case=False, ctx=ctx,
        )

        assert "error" not in result
        assert result["occurrencesReplaced"] == 3

    def test_atomic_batch_update(self):
        """All replacements in single batchUpdate — reverse order to preserve indices."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = _sample_doc(
            text="aa bb aa cc aa"
        )
        svc.documents().batchUpdate().execute.return_value = {"replies": [{}] * 6}
        ctx = _mock_ctx(docs_service=svc)

        replace_text_in_range(
            "doc123", "aa", "XX",
            start_index=1, end_index=15, ctx=ctx,
        )

        # Single batchUpdate call (filter out setup calls that have no kwargs)
        batch_calls = [
            c for c in svc.documents().batchUpdate.call_args_list
            if c[1]  # has keyword arguments
        ]
        assert len(batch_calls) == 1
        requests = batch_calls[0][1]["body"]["requests"]
        # 3 occurrences × 2 ops (delete + insert) = 6 requests
        assert len(requests) == 6

        # Verify reverse order (last match first to preserve earlier indices)
        first_delete = requests[0]["deleteContentRange"]["range"]
        second_delete = requests[2]["deleteContentRange"]["range"]
        third_delete = requests[4]["deleteContentRange"]["range"]
        assert first_delete["startIndex"] > second_delete["startIndex"]
        assert second_delete["startIndex"] > third_delete["startIndex"]


# ---------------------------------------------------------------------------
# replace_text_in_range — no match / edge cases
# ---------------------------------------------------------------------------


class TestReplaceTextInRangeEdgeCases:
    """Edge cases for replace_text_in_range."""

    def test_no_match_in_range(self):
        """No match within range returns informative result."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = _sample_doc(
            text="abc def ghi"
        )
        ctx = _mock_ctx(docs_service=svc)

        result = replace_text_in_range(
            "doc123", "xyz", "new", start_index=1, end_index=12, ctx=ctx
        )

        assert "error" not in result
        assert result["occurrencesReplaced"] == 0
        svc.documents().batchUpdate.assert_not_called()

    def test_replace_in_range_with_empty_string(self):
        """Replacing with empty string in range effectively deletes the text."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = _sample_doc(
            text="remove_me keep_me"
        )
        svc.documents().batchUpdate().execute.return_value = {"replies": [{}]}
        ctx = _mock_ctx(docs_service=svc)

        result = replace_text_in_range(
            "doc123", "remove_me", "",
            start_index=1, end_index=10, ctx=ctx,
        )

        assert "error" not in result
        assert result["occurrencesReplaced"] == 1
        # Only delete request, no insert
        batch_call = svc.documents().batchUpdate.call_args
        requests = batch_call[1]["body"]["requests"]
        assert len(requests) == 1
        assert "deleteContentRange" in requests[0]

    def test_api_error_returns_error_dict(self):
        """API error via safe_batch_update returns error dict, not exception."""
        svc = MagicMock()
        svc.documents().get().execute.return_value = _sample_doc(text="old text")
        svc.documents().batchUpdate().execute.side_effect = Exception("API down")
        ctx = _mock_ctx(docs_service=svc)

        result = replace_first_text("doc123", "old", "new", ctx=ctx)
        assert "error" in result

    def test_match_partially_overlapping_range_end_excluded(self):
        """A match that starts inside range but extends beyond is excluded."""
        svc = MagicMock()
        # "abcdef" at indices 1-7. Search "cdef" (indices 3-7) in range 1-5.
        svc.documents().get().execute.return_value = _sample_doc(text="abcdef")
        ctx = _mock_ctx(docs_service=svc)

        result = replace_text_in_range(
            "doc123", "cdef", "X", start_index=1, end_index=5, ctx=ctx
        )

        assert result["occurrencesReplaced"] == 0
        svc.documents().batchUpdate.assert_not_called()

    def test_match_starting_before_range_excluded(self):
        """A match that starts before range but ends inside is excluded."""
        svc = MagicMock()
        # "abcdef" at indices 1-7. Search "ab" (indices 1-3) in range 2-7.
        svc.documents().get().execute.return_value = _sample_doc(text="abcdef")
        ctx = _mock_ctx(docs_service=svc)

        result = replace_text_in_range(
            "doc123", "ab", "X", start_index=2, end_index=7, ctx=ctx
        )

        assert result["occurrencesReplaced"] == 0
        svc.documents().batchUpdate.assert_not_called()

    def test_document_not_found_raises(self):
        """API error when document doesn't exist propagates as exception."""
        svc = MagicMock()
        svc.documents().get().execute.side_effect = Exception("Document not found")
        ctx = _mock_ctx(docs_service=svc)

        try:
            replace_first_text("nonexistent", "foo", "bar", ctx=ctx)
            assert False, "Should have raised"
        except Exception as e:
            assert "Document not found" in str(e)

    def test_range_document_not_found_raises(self):
        """API error on get in replace_text_in_range propagates as exception."""
        svc = MagicMock()
        svc.documents().get().execute.side_effect = Exception("Document not found")
        ctx = _mock_ctx(docs_service=svc)

        try:
            replace_text_in_range(
                "nonexistent", "foo", "bar", 1, 10, ctx=ctx
            )
            assert False, "Should have raised"
        except Exception as e:
            assert "Document not found" in str(e)
