from __future__ import annotations

import time

import httpx

from mkv_subtitle_translator.models import DEFAULT_MODEL, SUBTITLE_MODELS, TranslationStats

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterClient:
    """HTTP client for OpenRouter API with retry logic"""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        max_retries: int = 3,
        timeout: float = 600.0,
    ):
        self.api_key = api_key
        self.model_key = model
        self.model_config = SUBTITLE_MODELS.get(model, SUBTITLE_MODELS[DEFAULT_MODEL])
        self.model_id = self.model_config["id"]
        self.max_retries = max_retries
        self.timeout = timeout
        self.stats = TranslationStats()

    def _make_request(self, messages: list[dict], temperature: float = 0.3, **kwargs) -> dict:
        """Make API request with retry logic"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/subtitle-translator",
            "X-Title": "Subtitle Translator",
        }

        max_tokens = kwargs.get("max_tokens", 500)

        payload = {
            "model": self.model_id,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        last_error = None
        for attempt in range(self.max_retries):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.post(OPENROUTER_API_URL, headers=headers, json=payload)

                    if response.status_code == 200:
                        return response.json()
                    elif response.status_code == 429:
                        # Rate limited - exponential backoff
                        wait_time = (2**attempt) * 2
                        time.sleep(wait_time)
                        continue
                    elif response.status_code >= 500:
                        # Server error - retry
                        wait_time = (2**attempt) * 1
                        time.sleep(wait_time)
                        continue
                    else:
                        error_msg = response.text
                        raise Exception(f"API error {response.status_code}: {error_msg}")

            except httpx.TimeoutException:
                last_error = "Request timeout"
                wait_time = (2**attempt) * 1
                time.sleep(wait_time)
            except Exception as e:
                last_error = str(e)
                if attempt < self.max_retries - 1:
                    wait_time = (2**attempt) * 1
                    time.sleep(wait_time)

        raise Exception(f"Failed after {self.max_retries} retries: {last_error}")

    def translate(
        self, system_prompt: str, user_prompt: str, max_tokens: int = 500
    ) -> tuple[str, int, int]:
        """Translate text and return (translation, input_tokens, output_tokens)"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        response = self._make_request(messages, max_tokens=max_tokens)

        translated_text = response["choices"][0]["message"]["content"].strip()

        usage = response.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)

        return translated_text, input_tokens, output_tokens

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Estimate cost based on token usage"""
        input_cost = (input_tokens / 1_000_000) * self.model_config["cost_per_1m_input"]
        output_cost = (output_tokens / 1_000_000) * self.model_config["cost_per_1m_output"]
        return input_cost + output_cost
