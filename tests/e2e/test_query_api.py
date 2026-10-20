"""
E2E tests – Query API endpoint.

Tests the FastAPI /query/ endpoint via the test client.  The QueryEngine
and underlying LLM/DB calls are mocked so the test does not require
a live API key or database for the engine logic.

Note: app/api/query.py creates a module-level QueryEngine() instance.
We patch the required dependencies before importing the app to prevent
real LLM/DB calls at import time.
"""
from unittest.mock import MagicMock, patch


def test_query_api_returns_200():
    """
    POST /query/?question=... should return HTTP 200 and a JSON body.

    QueryEngine.ask() is patched to return a deterministic response so
    the test does not depend on a live LLM or database.
    """
    # Patch OpenAI and DB connection before importing app so that the
    # module-level QueryEngine() in app/api/query.py does not make real calls.
    mock_ask_result = {
        "route": "SQL",
        "question": "Which products are currently low in stock?",
        "sql": "SELECT * FROM products;",
        "result": [("Widget", 5)],
        "answer": "Widget has low stock (5 units).",
    }

    with patch("app.gateway.llm_gateway.OpenAI"):
        with patch("app.ai.query_engine.execute_sql", return_value=[]):
            with patch("app.ai.query_engine.search_documents", return_value=[]):
                # Patch QueryEngine.ask so no real computation happens
                with patch("app.ai.query_engine.QueryEngine.ask", return_value=mock_ask_result):
                    from fastapi.testclient import TestClient
                    from main import app

                    client = TestClient(app)

                    response = client.post(
                        "/query/",
                        params={"question": "Which products are currently low in stock?"},
                    )

    assert response.status_code == 200
    assert response.json() is not None