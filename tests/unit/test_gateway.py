"""
Unit tests – LLM Gateway.

The LLMGateway.complete() call is mocked so the test suite does not
depend on a live LLM provider or API keys.
"""
from unittest.mock import MagicMock, patch

from app.gateway.llm_gateway import LLMGateway


def test_gateway_complete_returns_string():
    """
    LLMGateway.complete() should return the string content from the
    first successful model call.

    The underlying OpenAI client is mocked to avoid real network calls.
    """
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "Dynamic programming is a technique..."

    gateway = LLMGateway()

    with patch.object(gateway.client.chat.completions, "create", return_value=mock_response):
        result = gateway.complete("What is dynamic programming?")

    assert isinstance(result, str)
    assert len(result) > 0


def test_gateway_complete_falls_back_on_empty_content():
    """
    LLMGateway.complete() should try fallback models when the primary
    model returns empty content, raising RuntimeError if all fail.
    """
    # First call returns empty content; simulate by raising RuntimeError for all
    mock_empty = MagicMock()
    mock_empty.choices[0].message.content = None

    gateway = LLMGateway()

    with patch.object(
        gateway.client.chat.completions, "create", return_value=mock_empty
    ):
        import pytest
        with pytest.raises(RuntimeError):
            gateway.complete("test prompt")