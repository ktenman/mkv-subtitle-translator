from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path

from mkv_subtitle_translator.client import OpenRouterClient
from mkv_subtitle_translator.models import DEFAULT_MODEL, SUBTITLE_MODELS

REASONING_EFFORTS = ("low", "medium", "high", "xhigh", "max", "ultra")
DEFAULT_EFFORT = "high"

# One CLI call costs thousands of tokens of agent scaffolding regardless of
# payload, and takes 10s+, so translate in far bigger batches than the API path.
DEFAULT_BATCH_SIZE = 200
API_CHUNK_SIZE = 50

CLAUDE_MODEL = "claude"
CLAUDE_EFFORT = "max"
API_FALLBACK_MODEL = "gpt-5.6-sol"
TIMEOUT = 1800.0

CODEX_INSTALL_HINT = "codex CLI not found on PATH. Install: npm install -g @openai/codex"
CLAUDE_INSTALL_HINT = "claude CLI not found on PATH. See https://claude.com/claude-code"

# Covers codex (UsageLimitReached, QuotaExceeded, "rate limit") and Claude Code
# ("Usage limit reached", "Credit balance is too low", rate_limit_error). Kept
# specific on purpose: a false match demotes a free backend onto the paid one,
# and the text we search includes stdout, which echoes "[429] ..." subtitle lines.
_QUOTA_PATTERN = re.compile(
    r"usage.?limit|rate.?limit|too many requests|quota|credit balance"
    r"|out of credits|insufficient.{0,20}(credit|quota|balance|fund)",
    re.IGNORECASE,
)


class QuotaExhausted(RuntimeError):
    """A backend is out of credits - the next one in the chain should take over."""


def _error(name: str, detail: str) -> Exception:
    # Search the whole output, report only the tail: the quota line is often
    # buried above a long transcript, and truncating first would lose it.
    detail = detail.strip()
    quota = _QUOTA_PATTERN.search(detail)
    detail = detail[-500:]
    if quota:
        return QuotaExhausted(f"{name} is out of credits: {detail}")
    return RuntimeError(f"{name} failed: {detail}")


def _run(
    cmd: list[str], prompt: str, workdir: str, install_hint: str
) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            cmd, input=prompt, capture_output=True, text=True, timeout=TIMEOUT, cwd=workdir
        )
    except FileNotFoundError as exc:
        raise RuntimeError(install_hint) from exc


def _strip_code_fence(text: str) -> str:
    """Drop a ```-fenced wrapper if the model added one."""
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
    return "\n".join(lines).strip()


class CodexClient:
    """Translate through the local Codex CLI instead of a paid API.

    Runs on the ChatGPT subscription, so token usage and cost are always
    reported as zero. Same surface as OpenRouterClient.
    """

    def __init__(self, model: str = DEFAULT_MODEL, effort: str = DEFAULT_EFFORT):
        self.model_config = SUBTITLE_MODELS[model]
        self.model_id = self.model_config["id"]
        self.effort = effort

    def translate(
        self, system_prompt: str, user_prompt: str, max_tokens: int = 500
    ) -> tuple[str, int, int]:
        """Translate text and return (translation, 0, 0).

        max_tokens is ignored - codex exec has no output-length knob.
        """
        with tempfile.TemporaryDirectory() as workdir:
            last_message = Path(workdir) / "last_message.txt"
            cmd = [
                "codex",
                "exec",
                "--skip-git-repo-check",
                "--ephemeral",
                "--ignore-user-config",
                "--color",
                "never",
                "-s",
                "read-only",
                "-C",
                workdir,
                "-m",
                self.model_id,
                "-c",
                f"model_reasoning_effort={self.effort}",
                "-o",
                str(last_message),
                "-",
            ]
            result = _run(cmd, f"{system_prompt}\n\n{user_prompt}", workdir, CODEX_INSTALL_HINT)

            if result.returncode != 0:
                raise _error("codex", f"{result.stderr}\n{result.stdout}")

            text = ""
            if last_message.exists():
                text = last_message.read_text(encoding="utf-8").strip()

        if not text:
            raise RuntimeError("codex exec returned an empty response")

        return _strip_code_fence(text), 0, 0

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Always free - billed to the ChatGPT subscription, not per token."""
        return 0.0


class ClaudeClient:
    """Translate through the local Claude Code CLI.

    Runs on the Claude subscription. --tools "" matters a lot here: it drops
    the tool definitions the agent would otherwise send, cutting the per-call
    overhead from ~34k tokens to ~6.5k.
    """

    model_config = SUBTITLE_MODELS[CLAUDE_MODEL]

    def translate(
        self, system_prompt: str, user_prompt: str, max_tokens: int = 500
    ) -> tuple[str, int, int]:
        """Translate text and return (translation, 0, 0)."""
        with tempfile.TemporaryDirectory() as workdir:
            cmd = [
                "claude",
                "-p",
                "--model",
                self.model_config["id"],
                "--effort",
                CLAUDE_EFFORT,
                "--output-format",
                "json",
                "--strict-mcp-config",
                "--no-session-persistence",
                "--disable-slash-commands",
                "--tools",
                "",
                "--system-prompt",
                system_prompt,
            ]
            result = _run(cmd, user_prompt, workdir, CLAUDE_INSTALL_HINT)

        detail = f"{result.stderr}\n{result.stdout}"
        if result.returncode != 0:
            raise _error("claude", detail)

        try:
            last = json.loads(result.stdout)[-1]
        except (json.JSONDecodeError, IndexError, KeyError, TypeError) as exc:
            raise _error("claude", detail) from exc

        if last.get("is_error"):
            raise _error("claude", str(last.get("result") or detail))

        text = (last.get("result") or "").strip()
        if not text:
            raise RuntimeError("claude returned an empty response")

        return _strip_code_fence(text), 0, 0

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Always free - billed to the Claude subscription, not per token."""
        return 0.0


class FallbackClient:
    """Run the first backend that still has credits, in order.

    A backend that reports being out of credits is dropped for the rest of the
    run - no point retrying it on every batch.
    """

    def __init__(self, clients: list):
        self.clients = list(clients)

    @property
    def model_config(self) -> dict:
        return self.clients[0].model_config

    def translate(self, *args, **kwargs) -> tuple[str, int, int]:
        while True:
            try:
                return self.clients[0].translate(*args, **kwargs)
            except QuotaExhausted:
                if len(self.clients) == 1:
                    raise
                self.clients.pop(0)
                print(f"\nOut of credits - switching to {self.model_config['name']}")

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return self.clients[0].estimate_cost(input_tokens, output_tokens)


def uses_cli(model: str) -> bool:
    """True when the model translates through a local CLI instead of the API."""
    return "backend" in SUBTITLE_MODELS[model]


def build_chain(model: str = DEFAULT_MODEL, effort: str = DEFAULT_EFFORT, api_key: str = ""):
    """Codex -> Claude Code -> OpenRouter, entering at the requested backend.

    Each step takes over only once the one before it runs out of credits.
    OpenRouter is only reachable when an API key is available.
    """
    if not uses_cli(model):
        return OpenRouterClient(api_key, model)

    chain = []
    if SUBTITLE_MODELS[model]["backend"] == "codex":
        chain.append(CodexClient(model, effort))
    chain.append(ClaudeClient())
    if api_key:
        chain.append(OpenRouterClient(api_key, API_FALLBACK_MODEL))
    return FallbackClient(chain)
