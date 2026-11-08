"""
Integration tests – RAG document insertion.

Uses upsert_document() (idempotent) so repeated test runs do not create
duplicate rows in rag_documents.  All DB/embedding calls are inside
test functions.
"""
from app.rag.knowledge_generator import generate_daily_knowledge
from app.rag.vector_store import upsert_document


def test_rag_insert_daily_knowledge():
    """
    generate_daily_knowledge() produces a non-empty string that can be
    stored (upserted) into the rag_documents table without error.

    upsert_document is used instead of add_document to ensure the test
    is idempotent: re-running does not create duplicate records.
    """
    document = generate_daily_knowledge()

    assert isinstance(document, str), "Expected a string document"
    assert len(document) > 0, "Generated document is empty"

    result = upsert_document(
        content=document,
        metadata={
            "type": "daily_sales",
            "date": "test-fixture-2026-09-30",
        },
    )

    assert result is not None
    assert "action" in result, "'action' key missing from upsert result"
    assert result["action"] in ("inserted", "updated"), (
        f"Unexpected action: {result['action']}"
    )