from __future__ import annotations

from typer.testing import CliRunner

from mkv_subtitle_translator.cli import app
from mkv_subtitle_translator.models import DEFAULT_MODEL

runner = CliRunner()


def test_help_shows_usage():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Usage" in result.stdout


def test_list_models_exits_zero_and_shows_default_model():
    result = runner.invoke(app, ["--list-models"])
    assert result.exit_code == 0
    assert DEFAULT_MODEL in result.stdout


def test_unknown_model_is_rejected():
    result = runner.invoke(app, ["--model", "not-a-real-model", "--list-models"])
    assert result.exit_code != 0


def test_estimate_missing_file_errors():
    result = runner.invoke(app, ["--estimate", "/no/such/file.srt"])
    assert result.exit_code != 0
    assert "not found" in result.stdout.lower()


def test_estimate_existing_file_reports_cost(tmp_path):
    srt = tmp_path / "sample.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello there\n\n", encoding="utf-8")
    result = runner.invoke(app, ["--estimate", str(srt)])
    assert result.exit_code == 0
    assert "Cost Estimate" in result.stdout


def test_missing_api_key_errors_for_openrouter_models(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    result = runner.invoke(app, [str(tmp_path), "--model", "gpt-5.4"])
    assert result.exit_code != 0
    assert "API key required" in result.stdout


def test_codex_model_needs_no_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    result = runner.invoke(app, [str(tmp_path), "--model", "codex"])
    assert result.exit_code == 0
    assert "No files to translate" in result.stdout


def test_unknown_effort_is_rejected():
    result = runner.invoke(app, ["--effort", "turbo", "--list-models"])
    assert result.exit_code != 0
