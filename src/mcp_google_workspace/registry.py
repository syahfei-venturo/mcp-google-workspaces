"""Tool registry with fuzzy search capability."""

import re
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from typing import Any, Callable, Dict, List, Optional, Set


# Bidirectional synonym table for query expansion.
# Keys AND values are interchangeable — lookup builds the full synonym
# group for any member token.
_SYNONYM_GROUPS: List[Set[str]] = [
    {"add", "insert", "create", "write", "append", "new"},
    {"remove", "delete", "clear", "trash", "drop"},
    {"get", "read", "fetch", "retrieve", "export", "extract", "pull"},
    {"edit", "update", "modify", "change", "set", "patch"},
    {"find", "search", "query", "lookup", "filter", "discover"},
    {"list", "enumerate", "show", "browse"},
    {"share", "permission", "access", "collaborate"},
    {"format", "style", "theme", "appearance"},
    {"copy", "duplicate", "clone"},
    {"move", "rename", "transfer"},
    {"markdown", "md"},
    {"document", "doc", "page"},
    {"content", "body", "text"},
    {"convert", "transform"},
    {"draft", "compose", "generate"},
]

# Pre-computed lookup: token → set of synonyms (excluding itself)
_SYNONYMS: Dict[str, Set[str]] = {}
for _group in _SYNONYM_GROUPS:
    for _word in _group:
        _SYNONYMS.setdefault(_word, set()).update(_group - {_word})


@dataclass
class ToolParameter:
    """Describes a single parameter for a registered tool."""

    name: str
    type: str  # "string", "integer", "boolean", "array", "object"
    description: str
    required: bool = True
    default: Any = None


@dataclass
class ToolDefinition:
    """A registered tool with metadata for discovery."""

    name: str
    description: str
    parameters: List[ToolParameter]
    tags: List[str]
    fn: Callable
    category: str = ""
    read_only: bool = False


class ToolRegistry:
    """Registry of tools with fuzzy search.

    Tools are registered with metadata (name, description, parameters, tags)
    and can be discovered via fuzzy search or executed by exact name.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, ToolDefinition] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: List[ToolParameter],
        tags: List[str],
        fn: Callable,
        category: str = "",
        read_only: bool = False,
    ) -> None:
        """Register a tool in the registry."""
        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            parameters=parameters,
            tags=tags,
            fn=fn,
            category=category,
            read_only=read_only,
        )

    def get(self, name: str) -> Optional[ToolDefinition]:
        """Get a tool by exact name."""
        return self._tools.get(name)

    @property
    def tool_names(self) -> List[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    @property
    def categories(self) -> List[str]:
        """List all unique categories in the registry."""
        return sorted({t.category for t in self._tools.values() if t.category})

    def search(
        self, query: str, limit: int = 5, category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Fuzzy search tools by query string, optionally filtered by category.

        Matches against tool name, description, and tags using
        multiple scoring signals: exact match, substring, token
        overlap, and sequence similarity.

        When query is empty and no category is specified, returns a
        category summary so agents know what's available without
        listing every tool.

        Args:
            query: Search query (fuzzy matched)
            limit: Maximum results to return (default: 5)
            category: If provided, only return tools in this category
                      (e.g. "sheets", "docs")

        Returns:
            Sorted list of matching tools with metadata and score,
            or a category summary when query is empty.
        """
        pool = self._tools.values()
        if category:
            category_lower = category.lower()
            pool = [t for t in pool if t.category.lower() == category_lower]

        if not query.strip():
            # Empty query + specific category → list tools in that category
            if category:
                tools = list(pool)[:limit]
                return [self._tool_to_dict(t, 1.0) for t in tools]
            # Empty query + no category → return category summary
            return self._category_summary()

        scored: List[tuple[float, ToolDefinition]] = []
        for tool in pool:
            score = self._compute_score(query, tool)
            if score > 0.1:
                scored.append((score, tool))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [self._tool_to_dict(t, s) for s, t in scored[:limit]]

    def set_category(self, category: str) -> None:
        """Set category on all tools that don't have one yet.

        Intended to be called by service-level __init__.py after
        sub-module registration, so individual tools don't need
        to repeat the category string.

        Creates new ToolDefinition instances (immutable update).
        """
        for name, tool in self._tools.items():
            if not tool.category:
                self._tools[name] = replace(tool, category=category)

    def _category_summary(self) -> List[Dict[str, Any]]:
        """Build a summary of available categories with tool counts.

        Returns one entry per category, sorted alphabetically:
        [{"category": "docs", "tool_count": 12, "tools": ["get_document", ...]}]
        """
        groups: Dict[str, List[str]] = {}
        for tool in self._tools.values():
            cat = tool.category or "uncategorized"
            groups.setdefault(cat, []).append(tool.name)

        return [
            {
                "category": cat,
                "tool_count": len(names),
                "tools": sorted(names),
            }
            for cat, names in sorted(groups.items())
        ]

    def filter(self, enabled_tools: Set[str]) -> None:
        """Keep only tools in the enabled set, remove the rest."""
        self._tools = {
            name: tool for name, tool in self._tools.items() if name in enabled_tools
        }

    # Scoring weights — name is strongest, tokens (tags/name words) are
    # medium, description is weakest.  Sum = 1.0 so output stays in [0, 1].
    _W_NAME = 0.45
    _W_TOKENS = 0.35
    _W_DESC = 0.20

    def _compute_score(self, query: str, tool: ToolDefinition) -> float:
        """Compute fuzzy match score between query and tool.

        Weighted sum of three normalised signals (each 0–1):
        - Name:        45% — substring, containment, sequence similarity
        - Tokens:      35% — word-level prefix + synonym matching
        - Description: 20% — sequence similarity to description text

        A tool that matches moderately across all signals will outrank
        a tool that matches strongly on only one signal.
        """
        query_lower = query.lower()
        name_lower = tool.name.lower()

        if query_lower == name_lower:
            return 1.0

        name_score = self._score_name(query_lower, name_lower)
        token_score = self._score_tokens(query_lower, tool)
        desc_score = self._score_description(query_lower, tool.description.lower())

        return min(
            name_score * self._W_NAME
            + token_score * self._W_TOKENS
            + desc_score * self._W_DESC,
            1.0,
        )

    @staticmethod
    def _score_name(query: str, name: str) -> float:
        """Score based on name substring and sequence similarity.

        Returns 0.0–1.0 (normalised).
        """
        score = 0.0
        if query in name:
            score = max(score, 0.95)
        if name in query:
            score = max(score, 0.85)
        ratio = SequenceMatcher(None, query, name).ratio()
        return max(score, ratio)

    @staticmethod
    def _prefix_match(token: str, text_words: List[str]) -> bool:
        """Check if token prefix-matches any word in the list.

        Matches when:
        - Either side is a substring of the other ("read" in "reading")
        - They share a common prefix of >= 3 chars ("docs" ↔ "document")
        """
        for word in text_words:
            if token in word or word in token:
                return True
            # Common prefix length
            common = 0
            for a, b in zip(token, word):
                if a != b:
                    break
                common += 1
            if common >= 3:
                return True
        return False

    @staticmethod
    def _tokenize_text(text: str) -> List[str]:
        """Split text into lowercase words (by underscore, space, hyphen)."""
        return [w for w in re.split(r"[_\s\-]+", text.lower()) if w]

    @staticmethod
    def _expand_with_synonyms(token: str) -> List[str]:
        """Return the token plus its synonyms (if any)."""
        synonyms = _SYNONYMS.get(token)
        if not synonyms:
            return [token]
        return [token, *synonyms]

    def _token_matches(self, token: str, words: List[str]) -> bool:
        """Check if token (or any of its synonyms) prefix-matches words."""
        for candidate in self._expand_with_synonyms(token):
            if self._prefix_match(candidate, words):
                return True
        return False

    def _score_tokens(self, query: str, tool: ToolDefinition) -> float:
        """Score based on token overlap in name, tags, parameters, description.

        Uses prefix matching + synonym expansion for tolerance against
        truncation, inflection, and vocabulary differences.
        (e.g. "reading" matches "read", "fetch data" matches "get_sheet_data",
         "spreadsheet_id" matches tools with that parameter)

        Returns 0.0–1.0 (normalised). Takes the best signal among
        name-words, tags, parameter names, and description-words.
        """
        tokens = query.lower().split()
        if not tokens:
            return 0.0

        count = len(tokens)
        name_words = self._tokenize_text(tool.name)
        tag_words = self._tokenize_text(" ".join(tool.tags))
        param_words = self._tokenize_text(" ".join(p.name for p in tool.parameters))
        desc_words = self._tokenize_text(tool.description)

        name_hits = sum(1 for t in tokens if self._token_matches(t, name_words))
        tag_hits = sum(1 for t in tokens if self._token_matches(t, tag_words))
        param_hits = sum(1 for t in tokens if self._token_matches(t, param_words))
        desc_hits = sum(1 for t in tokens if self._token_matches(t, desc_words))

        return max(
            name_hits / count,
            tag_hits / count * 0.9,
            param_hits / count * 0.8,
            desc_hits / count * 0.7,
        )

    @staticmethod
    def _score_description(query: str, description: str) -> float:
        """Score based on sequence similarity to description.

        Returns 0.0–1.0 (normalised).
        """
        return SequenceMatcher(None, query, description).ratio()

    def _tool_to_dict(self, tool: ToolDefinition, score: float) -> Dict[str, Any]:
        """Serialize tool metadata for search results."""
        return {
            "name": tool.name,
            "description": tool.description,
            "category": tool.category,
            "parameters": [
                {
                    "name": p.name,
                    "type": p.type,
                    "description": p.description,
                    "required": p.required,
                    **({"default": p.default} if p.default is not None else {}),
                }
                for p in tool.parameters
            ],
            "read_only": tool.read_only,
            "score": round(score, 3),
        }
