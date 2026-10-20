"""
E2E tests – QueryEngine routing and SQL path.

QueryEngine orchestrates router → text-to-sql → execute_sql → answer.
We patch at the highest practical level (QueryEngine.ask itself for the
path that's already exercised by router unit tests, or at execute_sql
and gateway.complete level for richer integration coverage).
"""
from unittest.mock import MagicMock, patch


def test_query_engine_sql_route():
    """
    QueryEngine.ask() on a clearly SQL-routed question should return a
    dict with 'route' == 'SQL' and the standard keys.

    We patch:
    - OpenAI so LLMGateway constructor does not need API keys
    - execute_sql so no real DB query is run
    - Every LLMGateway.complete() so no real LLM call is made
    """
    mock_sql_result = [(72156,)]

    with patch("app.gateway.llm_gateway.OpenAI"):
        from app.ai.query_engine import QueryEngine
        engine = QueryEngine()

    # Patch complete() on every gateway instance inside the engine
    sql_answer = "There are 72,156 bills."
    with patch.object(engine.router.gateway, "complete", return_value="SQL"):
        with patch.object(engine.text_to_sql.gateway, "complete",
                          return_value="SELECT COUNT(*) AS total_bills FROM bills;"):
            with patch.object(engine.sql_answer_generator.gateway, "complete",
                              return_value=sql_answer):
                with patch("app.ai.query_engine.execute_sql", return_value=mock_sql_result):
                    # "how many bills" → SQL route (pattern match, no LLM needed)
                    result = engine.ask("How many bills are there?")

    assert result["route"] == "SQL"
    assert "sql" in result
    assert "result" in result
    assert "answer" in result


def test_query_engine_rag_route():
    """
    QueryEngine.ask() on a RAG-routed question should return a dict
    with 'route' == 'RAG', 'documents', and 'answer'.
    """
    mock_docs = [("Return policy text.", {"type": "policy"}, 0.95)]
    rag_answer = "Our return policy allows returns within 30 days."

    with patch("app.gateway.llm_gateway.OpenAI"):
        from app.ai.query_engine import QueryEngine
        engine = QueryEngine()

    with patch.object(engine.router.gateway, "complete", return_value="RAG"):
        with patch.object(engine.rag_answer_generator.gateway, "complete",
                          return_value=rag_answer):
            with patch("app.ai.query_engine.search_documents", return_value=mock_docs):
                # "return policy" → RAG route (pattern match, no LLM needed)
                result = engine.ask("What is our return policy?")

    assert result["route"] == "RAG"
    assert "documents" in result
    assert "answer" in result
    assert result["answer"] == rag_answer