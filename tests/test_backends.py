from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from mkv_subtitle_translator.backends import (
    ClaudeClient,
    CodexClient,
    FallbackClient,
    QuotaExhausted,
    build_chain,
)


def _fake_run(reply: str = "Tere", returncode: int = 0, stderr: str = ""):
    """Stand in for codex exec: write the reply to the -o file it was given."""

    def run(cmd, **kwargs):
        Path(cmd[cmd.index("-o") + 1]).write_text(reply, encoding="utf-8")
        return subprocess.CompletedProcess(cmd, returncode, "", stderr)

    return run


def _fake_claude_run(result: str = "Tere", is_error: bool = False):
    """Stand in for claude -p --output-format json."""
    stdout = json.dumps([{"type": "result", "is_error": is_error, "result": result}])

    def run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout, "")

    return run


class TestTranslate:
    def test_returns_last_message_with_zero_token_counts(self, mocker):
        mocker.patch("mkv_subtitle_translator.backends.subprocess.run", side_effect=_fake_run())
        client = CodexClient("codex")

        assert client.translate("system", "user") == ("Tere", 0, 0)

    def test_passes_model_and_effort_to_codex(self, mocker):
        run = mocker.patch(
            "mkv_subtitle_translator.backends.subprocess.run", side_effect=_fake_run()
        )
        CodexClient("codex", effort="max").translate("system", "user")

        cmd = run.call_args.args[0]
        assert cmd[:2] == ["codex", "exec"]
        assert cmd[cmd.index("-m") + 1] == "gpt-5.6-sol"
        assert cmd[cmd.index("-c") + 1] == "model_reasoning_effort=max"
        assert run.call_args.kwargs["input"] == "system\n\nuser"

    def test_strips_code_fence_from_reply(self, mocker):
        mocker.patch(
            "mkv_subtitle_translator.backends.subprocess.run",
            side_effect=_fake_run("```text\n[1] Tere\n```"),
        )

        text, _, _ = CodexClient("codex").translate("system", "user")
        assert text == "[1] Tere"

    def test_nonzero_exit_raises(self, mocker):
        mocker.patch(
            "mkv_subtitle_translator.backends.subprocess.run",
            side_effect=_fake_run(returncode=1, stderr="stream error"),
        )

        with pytest.raises(RuntimeError, match="stream error"):
            CodexClient("codex").translate("system", "user")

    def test_empty_reply_raises(self, mocker):
        mocker.patch(
            "mkv_subtitle_translator.backends.subprocess.run", side_effect=_fake_run("   ")
        )

        with pytest.raises(RuntimeError, match="empty response"):
            CodexClient("codex").translate("system", "user")

    def test_missing_codex_binary_raises_with_install_hint(self, mocker):
        mocker.patch(
            "mkv_subtitle_translator.backends.subprocess.run", side_effect=FileNotFoundError()
        )

        with pytest.raises(RuntimeError, match="npm install -g @openai/codex"):
            CodexClient("codex").translate("system", "user")

    @pytest.mark.parametrize(
        "stderr",
        [
            "stream error: UsageLimitReached",
            "QuotaExceeded: plan limit hit",
            "You've hit your usage limit",
            "rate limit: retry after 3600s",
        ],
    )
    def test_quota_errors_are_distinguishable(self, mocker, stderr):
        mocker.patch(
            "mkv_subtitle_translator.backends.subprocess.run",
            side_effect=_fake_run(returncode=1, stderr=stderr),
        )

        with pytest.raises(QuotaExhausted):
            CodexClient("codex").translate("system", "user")


class TestClaudeTranslate:
    def test_returns_result_field(self, mocker):
        mocker.patch(
            "mkv_subtitle_translator.backends.subprocess.run", side_effect=_fake_claude_run()
        )

        assert ClaudeClient().translate("system", "user") == ("Tere", 0, 0)

    def test_passes_model_effort_and_system_prompt(self, mocker):
        run = mocker.patch(
            "mkv_subtitle_translator.backends.subprocess.run", side_effect=_fake_claude_run()
        )
        ClaudeClient().translate("system", "user")

        cmd = run.call_args.args[0]
        assert cmd[:2] == ["claude", "-p"]
        assert cmd[cmd.index("--model") + 1] == "opus"
        assert cmd[cmd.index("--effort") + 1] == "max"
        assert cmd[cmd.index("--system-prompt") + 1] == "system"
        assert run.call_args.kwargs["input"] == "user"

    def test_error_result_raises(self, mocker):
        mocker.patch(
            "mkv_subtitle_translator.backends.subprocess.run",
            side_effect=_fake_claude_run("Something broke", is_error=True),
        )

        with pytest.raises(RuntimeError, match="Something broke"):
            ClaudeClient().translate("system", "user")

    def test_credit_error_is_quota_exhausted(self, mocker):
        mocker.patch(
            "mkv_subtitle_translator.backends.subprocess.run",
            side_effect=_fake_claude_run("Credit balance is too low", is_error=True),
        )

        with pytest.raises(QuotaExhausted):
            ClaudeClient().translate("system", "user")


class _StubClient:
    def __init__(self, name, reply=None):
        self.model_config = {"name": name}
        self.reply = reply
        self.calls = 0

    def translate(self, *args, **kwargs):
        self.calls += 1
        if self.reply is None:
            raise QuotaExhausted(f"{self.model_config['name']} is out of credits")
        return self.reply, 0, 0

    def estimate_cost(self, input_tokens, output_tokens):
        return 0.0


class TestFallbackClient:
    def test_uses_first_client_while_it_has_credits(self):
        first, second = _StubClient("first", "Tere"), _StubClient("second", "Tere teine")
        assert FallbackClient([first, second]).translate("s", "u") == ("Tere", 0, 0)
        assert second.calls == 0

    def test_switches_on_quota_and_stays_switched(self):
        first, second = _StubClient("first"), _StubClient("second", "Tere teine")
        chain = FallbackClient([first, second])

        assert chain.translate("s", "u") == ("Tere teine", 0, 0)
        chain.translate("s", "u")

        assert first.calls == 1  # not retried after it went dry
        assert chain.model_config["name"] == "second"

    def test_last_client_out_of_credits_propagates(self):
        chain = FallbackClient([_StubClient("first"), _StubClient("second")])

        with pytest.raises(QuotaExhausted):
            chain.translate("s", "u")


class TestBuildChain:
    def test_codex_falls_back_to_claude_then_openrouter(self):
        chain = build_chain("codex", "high", "sk-key")
        assert [type(c).__name__ for c in chain.clients] == [
            "CodexClient",
            "ClaudeClient",
            "OpenRouterClient",
        ]

    def test_openrouter_is_skipped_without_an_api_key(self):
        chain = build_chain("codex", "high", "")
        assert [type(c).__name__ for c in chain.clients] == ["CodexClient", "ClaudeClient"]

    def test_claude_model_starts_at_claude(self):
        chain = build_chain("claude", "high", "")
        assert [type(c).__name__ for c in chain.clients] == ["ClaudeClient"]

    def test_openrouter_model_is_used_directly(self):
        assert type(build_chain("gpt-5.4", "high", "sk-key")).__name__ == "OpenRouterClient"


class TestEstimateCost:
    def test_subscription_usage_is_free(self):
        assert CodexClient("codex").estimate_cost(1_000_000, 1_000_000) == 0.0
        assert ClaudeClient().estimate_cost(1_000_000, 1_000_000) == 0.0
