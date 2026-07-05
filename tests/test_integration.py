from __future__ import annotations

import os

import pytest

from mkv_subtitle_translator.client import OpenRouterClient
from mkv_subtitle_translator.models import DEFAULT_MODEL

pytestmark = pytest.mark.integration


@pytest.fixture
def api_key():
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        pytest.skip("OPENROUTER_API_KEY not set")
    return key


def test_translates_a_simple_sentence(api_key):
    client = OpenRouterClient(api_key, DEFAULT_MODEL)
    text, input_tokens, output_tokens = client.translate(
        "You are an expert English to Estonian subtitle translator. "
        "Return only the Estonian translation, nothing else.",
        '"Hello, how are you?"',
    )
    assert text.strip()
    assert input_tokens > 0
    assert output_tokens > 0
