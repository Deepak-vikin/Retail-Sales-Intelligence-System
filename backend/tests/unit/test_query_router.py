"""
Unit tests – QueryRouter.

QueryRouter uses keyword-pattern matching first; LLM fallback is only
reached when no known pattern matches.  These tests exercise the
pattern-matching paths and therefore do not need a live LLM.

The LLMGateway is patched at construction time so the test does not
require an API key or network access.
"""
from unittest.mock import MagicMock, patch

import pytest


def _make_router():
    """Instantiate QueryRouter with a mocked LLMGateway."""
    with patch("app.ai.query_router.LLMGateway") as MockGateway:
        MockGateway.return_value = MagicMock()
        from app.ai.query_router import QueryRouter
        return QueryRouter()


def test_sql_route():
    router = _make_router()
    assert router.route("What was the total revenue yesterday?") == "SQL"


def test_rag_route():
    router = _make_router()
    assert router.route("What is our return policy?") == "RAG"


def test_hybrid_route():
    router = _make_router()
    assert router.route("Why did revenue increase yesterday?") == "HYBRID"


def test_inventory_route():
    router = _make_router()
    assert router.route("Which products are currently low in stock?") == "SQL"


def test_purchase_route():
    router = _make_router()
    assert router.route("What stock was added today?") == "SQL"