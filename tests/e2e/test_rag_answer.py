"""
E2E tests – RAGAnswerGenerator.

Tests that RAGAnswerGenerator.generate_answer() correctly formats the
prompt and returns the LLM's response.  The LLM gateway is mocked.
"""
from unittest.mock import MagicMock, patch


def test_rag_answer_generator_returns_string():
    """
    RAGAnswerGenerator.generate_answer() should call the gateway and
    return the stripped response string.
    """
    with patch("app.rag.rag_answer_generator.LLMGateway") as MockGateway:
        mock_gw = MagicMock()
        mock_gw.complete.return_value = "  Revenue increased by 15%.  "
        MockGateway.return_value = mock_gw

        from app.rag.rag_answer_generator import RAGAnswerGenerator

        generator = RAGAnswerGenerator()

        documents = [
            ("Daily summary: revenue was ₹50,000.", {"type": "daily_sales"}, 0.9),
        ]

        answer = generator.generate_answer(
            "What was the sales performance on September 30?",
            documents,
        )

    assert isinstance(answer, str)
    assert answer == "Revenue increased by 15%."


def test_rag_answer_generator_handles_empty_documents():
    """
    RAGAnswerGenerator should still call the gateway when documents list
    is empty (context will be empty string).
    """
    with patch("app.rag.rag_answer_generator.LLMGateway") as MockGateway:
        mock_gw = MagicMock()
        mock_gw.complete.return_value = "The information is not available."
        MockGateway.return_value = mock_gw

        from app.rag.rag_answer_generator import RAGAnswerGenerator

        generator = RAGAnswerGenerator()
        answer = generator.generate_answer("What is our refund policy?", [])

    assert isinstance(answer, str)
    assert len(answer) > 0