
"""
Unit tests - LLM Gateway.

The OpenAI client is mocked so tests require no API key
or live LLM provider.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.gateway.llm_gateway import LLMGateway


@patch("app.gateway.llm_gateway.OpenAI")
def test_gateway_complete_returns_string(mock_openai):
    """Return string content from a successful model call."""

    mock_client = MagicMock()
    mock_openai.return_value = mock_client

    mock_response = MagicMock()
    mock_response.choices[0].message.content = (
        "Dynamic programming is a technique..."
    )

    mock_client.chat.completions.create.return_value = mock_response

    gateway = LLMGateway()
    result = gateway.complete("What is dynamic programming?")

    assert isinstance(result, str)
    assert len(result) > 0
    mock_client.chat.completions.create.assert_called()


@patch("app.gateway.llm_gateway.OpenAI")
def test_gateway_complete_falls_back_on_empty_content(mock_openai):
    """Raise RuntimeError when all model attempts return empty content."""

    mock_client = MagicMock()
    mock_openai.return_value = mock_client

    mock_response = MagicMock()
    mock_response.choices[0].message.content = None

    mock_client.chat.completions.create.return_value = mock_response

    gateway = LLMGateway()

    with pytest.raises(RuntimeError):
        gateway.complete("test prompt")
