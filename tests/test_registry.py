"""Tests for the tool registry and fuzzy search."""

from mcp_google_workspace.registry import ToolParameter, ToolRegistry


def _make_registry() -> ToolRegistry:
    """Create a registry with sample tools for testing."""
    registry = ToolRegistry()

    registry.register(
        name="get_sheet_data",
        description="Get data from a specific sheet in a Google Spreadsheet.",
        parameters=[
            ToolParameter("spreadsheet_id", "string", "The spreadsheet ID"),
            ToolParameter("sheet", "string", "The sheet name"),
        ],
        tags=["read", "data", "values"],
        fn=lambda **kwargs: None,
        category="sheets",
        read_only=True,
    )

    registry.register(
        name="update_cells",
        description="Write data to a specific range in a sheet.",
        parameters=[
            ToolParameter("spreadsheet_id", "string", "The spreadsheet ID"),
            ToolParameter("range", "string", "A1 notation range"),
            ToolParameter("data", "array", "2D array of values"),
        ],
        tags=["write", "update", "cells"],
        fn=lambda **kwargs: None,
        category="sheets",
    )

    registry.register(
        name="create_spreadsheet",
        description="Create a new Google Spreadsheet.",
        parameters=[
            ToolParameter("title", "string", "Spreadsheet title"),
        ],
        tags=["create", "spreadsheet", "new"],
        fn=lambda **kwargs: None,
        category="sheets",
    )

    registry.register(
        name="add_chart",
        description="Create a chart from spreadsheet data.",
        parameters=[
            ToolParameter("spreadsheet_id", "string", "The spreadsheet ID"),
            ToolParameter("chart_type", "string", "Chart type"),
        ],
        tags=["chart", "visualization"],
        fn=lambda **kwargs: None,
        category="sheets",
    )

    registry.register(
        name="get_document",
        description="Get the full structure of a Google Document.",
        parameters=[
            ToolParameter("document_id", "string", "The document ID"),
        ],
        tags=["read", "document", "structure"],
        fn=lambda **kwargs: None,
        category="docs",
        read_only=True,
    )

    registry.register(
        name="insert_text",
        description="Insert text into a Google Document at a position.",
        parameters=[
            ToolParameter("document_id", "string", "The document ID"),
            ToolParameter("text", "string", "Text to insert"),
            ToolParameter("index", "integer", "Character index"),
        ],
        tags=["write", "text", "insert"],
        fn=lambda **kwargs: None,
        category="docs",
    )

    return registry


class TestToolRegistry:
    """Tests for ToolRegistry core operations."""

    def test_register_and_get(self):
        registry = _make_registry()
        tool = registry.get("get_sheet_data")
        assert tool is not None
        assert tool.name == "get_sheet_data"
        assert tool.read_only is True

    def test_get_nonexistent(self):
        registry = _make_registry()
        assert registry.get("nonexistent") is None

    def test_tool_names(self):
        registry = _make_registry()
        names = registry.tool_names
        assert "get_sheet_data" in names
        assert "update_cells" in names
        assert "create_spreadsheet" in names
        assert "add_chart" in names

    def test_filter(self):
        registry = _make_registry()
        registry.filter({"get_sheet_data", "add_chart"})
        assert len(registry.tool_names) == 2
        assert "get_sheet_data" in registry.tool_names
        assert "add_chart" in registry.tool_names
        assert "update_cells" not in registry.tool_names


class TestToolSearch:
    """Tests for fuzzy search functionality."""

    def test_exact_name_match(self):
        registry = _make_registry()
        results = registry.search("get_sheet_data")
        assert len(results) > 0
        assert results[0]["name"] == "get_sheet_data"
        assert results[0]["score"] == 1.0

    def test_partial_name_match(self):
        registry = _make_registry()
        results = registry.search("sheet_data")
        assert len(results) > 0
        assert results[0]["name"] == "get_sheet_data"

    def test_tag_match(self):
        registry = _make_registry()
        results = registry.search("chart")
        assert any(r["name"] == "add_chart" for r in results)

    def test_description_match(self):
        registry = _make_registry()
        results = registry.search("write data")
        assert any(r["name"] == "update_cells" for r in results)

    def test_empty_query_returns_category_summary(self):
        """Empty query without category returns category summary."""
        registry = _make_registry()
        results = registry.search("")
        assert len(results) > 0
        # Should be category summary, not individual tools
        assert "category" in results[0]
        assert "tool_count" in results[0]
        assert "tools" in results[0]

    def test_limit_parameter(self):
        registry = _make_registry()
        results = registry.search("", limit=2)
        assert len(results) <= 2

    def test_result_contains_parameters(self):
        registry = _make_registry()
        results = registry.search("get_sheet_data")
        assert "parameters" in results[0]
        param_names = [p["name"] for p in results[0]["parameters"]]
        assert "spreadsheet_id" in param_names

    def test_result_contains_read_only(self):
        registry = _make_registry()
        results = registry.search("get_sheet_data")
        assert results[0]["read_only"] is True

    def test_no_match_returns_empty(self):
        registry = _make_registry()
        results = registry.search("zzzznonexistent")
        # Might return low-score results; check top score is low
        if results:
            assert results[0]["score"] < 0.5

    def test_multi_token_query(self):
        registry = _make_registry()
        results = registry.search("read data values")
        assert any(r["name"] == "get_sheet_data" for r in results)

    def test_result_contains_category(self):
        registry = _make_registry()
        results = registry.search("get_sheet_data")
        assert results[0]["category"] == "sheets"


class TestCategoryFilter:
    """Tests for category-based filtering."""

    def test_categories_property(self):
        registry = _make_registry()
        cats = registry.categories
        assert "sheets" in cats
        assert "docs" in cats
        assert len(cats) == 2

    def test_search_with_category_sheets(self):
        registry = _make_registry()
        results = registry.search("read", category="sheets")
        for r in results:
            assert r["category"] == "sheets"

    def test_search_with_category_docs(self):
        registry = _make_registry()
        results = registry.search("read", category="docs")
        for r in results:
            assert r["category"] == "docs"

    def test_search_with_category_filters_correctly(self):
        """Query 'read' matches both services — category narrows to one."""
        registry = _make_registry()
        all_results = registry.search("read", limit=10)
        sheets_results = registry.search("read", limit=10, category="sheets")
        docs_results = registry.search("read", limit=10, category="docs")

        all_names = {r["name"] for r in all_results}
        sheets_names = {r["name"] for r in sheets_results}
        docs_names = {r["name"] for r in docs_results}

        # Filtered results are subsets of unfiltered
        assert sheets_names <= all_names
        assert docs_names <= all_names
        # No overlap between categories
        assert sheets_names.isdisjoint(docs_names)

    def test_search_with_category_case_insensitive(self):
        registry = _make_registry()
        results = registry.search("read", category="SHEETS")
        assert len(results) > 0
        assert all(r["category"] == "sheets" for r in results)

    def test_search_with_unknown_category_returns_empty(self):
        registry = _make_registry()
        results = registry.search("read", category="slides")
        assert results == []

    def test_empty_query_with_category(self):
        registry = _make_registry()
        results = registry.search("", category="docs")
        assert len(results) > 0
        assert all(r["category"] == "docs" for r in results)

    def test_set_category_on_uncategorized(self):
        registry = ToolRegistry()
        registry.register(
            name="tool_a",
            description="A tool",
            parameters=[],
            tags=[],
            fn=lambda **kwargs: None,
        )
        registry.register(
            name="tool_b",
            description="B tool",
            parameters=[],
            tags=[],
            fn=lambda **kwargs: None,
            category="existing",
        )
        registry.set_category("new_cat")

        assert registry.get("tool_a").category == "new_cat"
        # Already categorized tool is not overwritten
        assert registry.get("tool_b").category == "existing"


class TestPrefixTokenMatching:
    """Tests for prefix/partial token matching in search."""

    def test_inflected_verb_matches_tag(self):
        """'reading' should match tools tagged 'read'."""
        registry = _make_registry()
        results = registry.search("reading", limit=10)
        assert any(r["name"] == "get_sheet_data" for r in results)

    def test_inflected_verb_matches_name(self):
        """'creating' should match 'create_spreadsheet'."""
        registry = _make_registry()
        results = registry.search("creating", limit=10)
        assert any(r["name"] == "create_spreadsheet" for r in results)

    def test_plural_matches_singular_tag(self):
        """'writes' should match tools tagged 'write'."""
        registry = _make_registry()
        results = registry.search("writes", limit=10)
        assert any(r["name"] == "update_cells" for r in results)

    def test_abbreviation_matches_full_word(self):
        """'doc' should match 'document' in description/name."""
        registry = _make_registry()
        results = registry.search("doc", limit=10)
        assert any(r["name"] == "get_document" for r in results)

    def test_truncated_query_matches(self):
        """'spread' should match 'spreadsheet'."""
        registry = _make_registry()
        results = registry.search("spread", limit=10)
        assert any(r["name"] == "create_spreadsheet" for r in results)

    def test_short_token_no_false_positive(self):
        """Very short tokens (< 3 chars) should not over-match."""
        registry = _make_registry()
        results = registry.search("zz", limit=10)
        # Should not match anything meaningful
        if results:
            assert results[0]["score"] < 0.5

    def test_multi_token_prefix_match(self):
        """'inserting text' should match 'insert_text'."""
        registry = _make_registry()
        results = registry.search("inserting text", limit=10)
        assert any(r["name"] == "insert_text" for r in results)


class TestSynonymExpansion:
    """Tests for synonym-based query expansion."""

    def test_fetch_matches_read_tools(self):
        """'fetch' is a synonym of 'read' — should match get_sheet_data."""
        registry = _make_registry()
        results = registry.search("fetch data", limit=10)
        assert any(r["name"] == "get_sheet_data" for r in results)

    def test_remove_matches_delete_tools(self):
        """'remove' is a synonym of 'delete' — no delete tool in fixture,
        but should not crash."""
        registry = _make_registry()
        results = registry.search("remove", limit=10)
        # Should not error; results depend on description matching
        assert isinstance(results, list)

    def test_modify_matches_update_tools(self):
        """'modify' is a synonym of 'update' — should match update_cells."""
        registry = _make_registry()
        results = registry.search("modify cells", limit=10)
        assert any(r["name"] == "update_cells" for r in results)

    def test_retrieve_matches_get_tools(self):
        """'retrieve' is a synonym of 'get/read' — should match read tools."""
        registry = _make_registry()
        results = registry.search("retrieve document", limit=10)
        assert any(r["name"] == "get_document" for r in results)

    def test_new_matches_create_tools(self):
        """'new' is a synonym of 'create' — should match create_spreadsheet."""
        registry = _make_registry()
        results = registry.search("new spreadsheet", limit=10)
        assert any(r["name"] == "create_spreadsheet" for r in results)

    def test_direct_match_still_ranks_higher(self):
        """Direct token match should score >= synonym match."""
        registry = _make_registry()
        direct = registry.search("create spreadsheet", limit=1)
        synonym = registry.search("new spreadsheet", limit=1)
        assert direct[0]["score"] >= synonym[0]["score"]

    def test_unknown_word_no_synonym_expansion(self):
        """Words not in synonym table should not match via synonyms."""
        registry = _make_registry()
        results = registry.search("banana", limit=10)
        # May still get low scores from SequenceMatcher description matching,
        # but should not rank highly
        if results:
            assert results[0]["score"] < 0.7


class TestWeightedSumScoring:
    """Tests for weighted sum scoring behavior."""

    def test_exact_name_match_is_1(self):
        """Exact name match short-circuits to 1.0."""
        registry = _make_registry()
        results = registry.search("get_sheet_data")
        assert results[0]["score"] == 1.0

    def test_score_in_valid_range(self):
        """All scores should be between 0 and 1."""
        registry = _make_registry()
        for query in ["read", "create", "chart", "update cells", "x"]:
            results = registry.search(query, limit=10)
            for r in results:
                assert 0.0 <= r["score"] <= 1.0, (
                    f"query={query!r} tool={r['name']} score={r['score']}"
                )

    def test_multi_signal_outranks_single_signal(self):
        """A tool matching name + tags + description should score higher
        than a tool matching only description with similar strength."""
        registry = _make_registry()
        # "get sheet data" matches get_sheet_data on:
        #   - name (contains "get", "sheet", "data")
        #   - tags ("read", "data", "values")
        #   - description (contains "data", "sheet")
        results = registry.search("get sheet data", limit=10)
        top = results[0]
        assert top["name"] == "get_sheet_data"
        # Should be a strong score due to multi-signal match
        assert top["score"] > 0.4

    def test_threshold_filters_noise(self):
        """Very low scoring results (< 0.1) should be filtered out."""
        registry = _make_registry()
        results = registry.search("xyznonexistent", limit=10)
        for r in results:
            assert r["score"] >= 0.1


class TestParameterSearch:
    """Tests for parameter-name-based search."""

    def test_spreadsheet_id_matches_sheets_tools(self):
        """Searching 'spreadsheet_id' should find tools with that parameter."""
        registry = _make_registry()
        results = registry.search("spreadsheet_id", limit=10)
        matched_names = {r["name"] for r in results}
        # All sheets tools that have spreadsheet_id parameter
        assert "get_sheet_data" in matched_names
        assert "update_cells" in matched_names
        assert "add_chart" in matched_names

    def test_document_id_matches_docs_tools(self):
        """Searching 'document_id' should find tools with that parameter."""
        registry = _make_registry()
        results = registry.search("document_id", limit=10)
        matched_names = {r["name"] for r in results}
        assert "get_document" in matched_names
        assert "insert_text" in matched_names

    def test_chart_type_matches_chart_tool(self):
        """Searching 'chart_type' should find add_chart."""
        registry = _make_registry()
        results = registry.search("chart_type", limit=10)
        assert any(r["name"] == "add_chart" for r in results)

    def test_name_match_outranks_param_match(self):
        """Direct name match should rank higher than parameter-only match."""
        registry = _make_registry()
        name_results = registry.search("add_chart", limit=1)
        param_results = registry.search("chart_type", limit=1)
        # Exact name match = 1.0, parameter match < 1.0
        assert name_results[0]["score"] > param_results[0]["score"]


class TestCategorySummary:
    """Tests for empty query category summary behavior."""

    def test_empty_query_returns_all_categories(self):
        registry = _make_registry()
        results = registry.search("")
        cats = {r["category"] for r in results}
        assert "sheets" in cats
        assert "docs" in cats

    def test_summary_has_correct_tool_counts(self):
        registry = _make_registry()
        results = registry.search("")
        by_cat = {r["category"]: r for r in results}
        # Fixture: 4 sheets tools, 2 docs tools
        assert by_cat["sheets"]["tool_count"] == 4
        assert by_cat["docs"]["tool_count"] == 2

    def test_summary_tools_are_sorted(self):
        registry = _make_registry()
        results = registry.search("")
        for entry in results:
            assert entry["tools"] == sorted(entry["tools"])

    def test_summary_lists_tool_names(self):
        registry = _make_registry()
        results = registry.search("")
        by_cat = {r["category"]: r for r in results}
        assert "get_sheet_data" in by_cat["sheets"]["tools"]
        assert "get_document" in by_cat["docs"]["tools"]

    def test_empty_query_with_category_returns_tools_not_summary(self):
        """Empty query + category filter should still return tool dicts."""
        registry = _make_registry()
        results = registry.search("", category="sheets")
        assert len(results) > 0
        # Should be tool dicts, not summary
        assert "name" in results[0]
        assert "parameters" in results[0]

    def test_whitespace_query_same_as_empty(self):
        registry = _make_registry()
        empty = registry.search("")
        spaces = registry.search("   ")
        assert empty == spaces
