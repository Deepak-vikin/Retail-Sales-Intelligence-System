"""
Integration tests – RAG document search.

Verifies that search_documents() returns a list of tuples with the
expected structure (content, metadata, similarity).
All calls are inside test functions (not at import time).
"""
from app.rag.vector_store import search_documents


def test_rag_search_returns_results():
    """
    search_documents() should return a list.
    Each element should be a tuple of (content, metadata, similarity).
    """
    results = search_documents(
        "What was the sales performance on September 30?",
        limit=3,
    )

    assert isinstance(results, list), "Expected a list of results"

    for row in results:
        assert len(row) == 3, (
            f"Expected tuple of 3 (content, metadata, similarity), got {len(row)}"
        )
        content, metadata, similarity = row
        assert isinstance(content, str), "content should be a string"
        assert isinstance(similarity, float), "similarity should be a float"