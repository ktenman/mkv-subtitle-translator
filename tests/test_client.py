from __future__ import annotations

import httpx
import pytest

from mkv_subtitle_translator.client import OpenRouterClient


def mock_transport(mocker, handler):
    client_class = httpx.Client
    transport = httpx.MockTransport(handler)
    mocker.patch(
        "mkv_subtitle_translator.client.httpx.Client",
        side_effect=lambda **kwargs: client_class(transport=transport, **kwargs),
    )


@pytest.mark.parametrize("failure", [429, 503, "timeout"])
def test_retry_progress_precedes_backoff_and_next_attempt(mocker, failure):
    messages = []
    at_request = []
    at_backoff = []

    def handler(request):
        at_request.append(messages[-1])
        if len(at_request) == 1:
            if failure == "timeout":
                raise httpx.ReadTimeout("private details", request=request)
            return httpx.Response(failure, text="private details")
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Tere"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )

    mock_transport(mocker, handler)
    mocker.patch(
        "mkv_subtitle_translator.client.time.sleep",
        side_effect=lambda delay: at_backoff.append((delay, messages[-1])),
    )
    client = OpenRouterClient("key", "gpt-5.4", max_retries=3)

    assert client.translate("system", "user", progress=messages.append) == ("Tere", 10, 5)
    assert "attempt 1/3" in at_request[0]
    assert "attempt 2/3" in at_request[1]
    assert "timeout 600s" in at_request[0]
    assert len(at_backoff) == 1
    assert at_backoff[0][0] == (2 if failure == 429 else 1)
    assert "retrying in" in at_backoff[0][1]
    assert "private details" not in " ".join(messages)


def test_exhausted_retries_report_the_reason_without_another_backoff(mocker):
    messages = []
    waits = []
    mock_transport(mocker, lambda request: httpx.Response(429, text="private details"))
    mocker.patch("mkv_subtitle_translator.client.time.sleep", side_effect=waits.append)
    client = OpenRouterClient("key", "gpt-5.4", max_retries=2)

    with pytest.raises(Exception, match="429"):
        client.translate("system", "user", progress=messages.append)

    assert waits == [2]
    assert "attempt 2/2" in messages[-1]
    assert "retrying" not in messages[-1]
