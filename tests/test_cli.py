from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mkv_subtitle_translator.cli import app
from mkv_subtitle_translator.models import DEFAULT_MODEL
from mkv_subtitle_translator.translator import TranslationFailed

runner = CliRunner()

SRT = "1\n00:00:01,000 --> 00:00:02,000\nHi\n\n"


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


@pytest.mark.parametrize("size", ["0", "-5"])
def test_non_positive_chunk_size_is_rejected(size):
    # A non-positive size yields zero batches, which would write English as Estonian.
    result = runner.invoke(app, ["--chunk-size", size, "--list-models"])
    assert result.exit_code != 0


def test_estimate_adds_the_term_sheet_for_batch_models_only():
    from mkv_subtitle_translator.cli import _estimated_tokens

    assert _estimated_tokens(964, "gpt-5.4-pro") == (144_600, 28_920)
    assert _estimated_tokens(964, "gpt-5.6-sol") == (638_168, 29_920)
    assert _estimated_tokens(2_790, "gpt-5.6-sol")[0] == 4_357_980


def test_translates_through_translate_file(tmp_path, mocker):
    srt = tmp_path / "show.extracted.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:02,000\nHi\n\n", encoding="utf-8")
    translate_file = mocker.patch("mkv_subtitle_translator.cli.OpenRouterTranslator.translate_file")

    result = runner.invoke(app, ["-f", str(srt), "--model", "codex"])

    assert result.exit_code == 0
    assert translate_file.call_args.args[1] == str(tmp_path / "show.et.srt")
    assert translate_file.call_args.kwargs["source_name"] == "show.extracted.srt"


def test_a_finished_translation_is_skipped(tmp_path, mocker):
    srt = tmp_path / "show.extracted.srt"
    srt.write_text(SRT, encoding="utf-8")
    (tmp_path / "show.et.srt").touch()
    translate_file = mocker.patch("mkv_subtitle_translator.cli.OpenRouterTranslator.translate_file")

    result = runner.invoke(app, ["-f", str(srt), "--model", "codex"])

    assert result.exit_code == 0
    assert "output exists" in result.stdout
    translate_file.assert_not_called()


def test_an_unfinished_check_is_finished_instead_of_skipped(tmp_path, mocker):
    srt = tmp_path / "show.extracted.srt"
    srt.write_text(SRT, encoding="utf-8")
    (tmp_path / "show.et.srt").touch()
    (tmp_path / "show.et.unchecked").touch()
    translate_file = mocker.patch("mkv_subtitle_translator.cli.OpenRouterTranslator.translate_file")

    result = runner.invoke(app, ["-f", str(srt), "--model", "codex"])

    assert result.exit_code == 0
    assert translate_file.call_args.kwargs["check_only"] is True


def test_force_translates_again_even_with_an_unfinished_check(tmp_path, mocker):
    srt = tmp_path / "show.extracted.srt"
    srt.write_text(SRT, encoding="utf-8")
    (tmp_path / "show.et.srt").touch()
    (tmp_path / "show.et.unchecked").touch()
    translate_file = mocker.patch("mkv_subtitle_translator.cli.OpenRouterTranslator.translate_file")

    result = runner.invoke(app, ["-f", str(srt), "--model", "codex", "--force"])

    assert result.exit_code == 0
    assert translate_file.call_args.kwargs["check_only"] is False


def test_line_by_line_models_have_no_check_to_finish(tmp_path, mocker):
    srt = tmp_path / "show.extracted.srt"
    srt.write_text(SRT, encoding="utf-8")
    (tmp_path / "show.et.srt").touch()
    (tmp_path / "show.et.unchecked").touch()
    translate_file = mocker.patch("mkv_subtitle_translator.cli.OpenRouterTranslator.translate_file")

    result = runner.invoke(app, ["-f", str(srt), "--model", "gpt-5.4-pro", "--api-key", "key"])

    assert result.exit_code == 0
    translate_file.assert_not_called()


@pytest.mark.parametrize("folder", [".", "season[/b]"])
def test_a_name_too_long_to_save_is_a_clear_error(tmp_path, mocker, folder):
    long_name = tmp_path / folder / f"{'a' * 244}.srt"
    long_name.parent.mkdir(parents=True, exist_ok=True)
    long_name.write_text(SRT, encoding="utf-8")
    run = mocker.patch(
        "mkv_subtitle_translator.backends.subprocess.run",
        return_value=subprocess.CompletedProcess([], 1, "", "Not logged in"),
    )

    result = runner.invoke(app, ["-f", str(long_name)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "too long" in result.stdout
    assert "Not finished" in result.stdout
    run.assert_not_called()


def test_missing_reference_file_is_rejected():
    result = runner.invoke(app, ["--reference", "/no/such/file.srt", "--list-models"])
    assert result.exit_code != 0


def test_reference_files_reach_translate_file(tmp_path, mocker):
    srt = tmp_path / "show.extracted.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:02,000\nHi\n\n", encoding="utf-8")
    one, two = tmp_path / "one.srt", tmp_path / "two.srt"
    one.touch()
    two.touch()
    translate_file = mocker.patch("mkv_subtitle_translator.cli.OpenRouterTranslator.translate_file")

    args = ["-f", str(srt), "--reference", str(one), "--reference", str(two)]
    result = runner.invoke(app, args)

    assert result.exit_code == 0
    assert translate_file.call_args.kwargs["references"] == [str(one), str(two)]


def test_no_installed_backend_stops_with_the_install_hint(tmp_path, mocker, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    srt = tmp_path / "show.extracted.srt"
    srt.write_text(SRT, encoding="utf-8")
    mocker.patch("mkv_subtitle_translator.backends.subprocess.run", side_effect=FileNotFoundError())

    result = runner.invoke(app, ["-f", str(srt)])

    assert result.exit_code == 1
    assert "not found on PATH" in result.stdout
    assert not (tmp_path / "show.et.srt").exists()


def test_a_backend_that_fails_leaves_no_output_and_merges_nothing(tmp_path, mocker):
    video = tmp_path / "show.mkv"
    video.touch()
    srt = tmp_path / "show.extracted.srt"
    srt.write_text(SRT, encoding="utf-8")
    mocker.patch(
        "mkv_subtitle_translator.cli.extract_best_subtitle_from_mkv", return_value=str(srt)
    )
    mocker.patch(
        "mkv_subtitle_translator.backends.subprocess.run",
        return_value=subprocess.CompletedProcess([], 1, "", "Not logged in"),
    )
    merge = mocker.patch("mkv_subtitle_translator.cli.merge_subtitles_into_mkv")

    result = runner.invoke(app, ["-f", str(video)])

    assert result.exit_code == 1
    assert "1 of 1 subtitles were not translated" in result.stdout
    assert not (tmp_path / "show.et.srt").exists()
    merge.assert_not_called()


def _extract_to_disk(mocker):
    def extract(mkv):
        srt = Path(mkv).with_suffix(".extracted.srt")
        srt.write_text(SRT, encoding="utf-8")
        return str(srt)

    return mocker.patch(
        "mkv_subtitle_translator.cli.extract_best_subtitle_from_mkv", side_effect=extract
    )


def _outputs(translate_file):
    return sorted(Path(call.args[1]).name for call in translate_file.call_args_list)


def test_folder_run_adds_new_videos_to_the_ones_already_extracted(tmp_path, mocker):
    (tmp_path / "old.mkv").touch()
    (tmp_path / "old.extracted.srt").write_text(SRT, encoding="utf-8")
    (tmp_path / "new.mkv").touch()
    extract = _extract_to_disk(mocker)
    translate_file = mocker.patch("mkv_subtitle_translator.cli.OpenRouterTranslator.translate_file")

    result = runner.invoke(app, [str(tmp_path)])

    assert result.exit_code == 0
    extract.assert_called_once_with(str(tmp_path / "new.mkv"))
    assert _outputs(translate_file) == ["new.et.srt", "old.et.srt"]


def test_force_extracts_again_and_keeps_subtitles_with_no_video(tmp_path, mocker):
    (tmp_path / "video.mkv").touch()
    (tmp_path / "video.extracted.srt").write_text(SRT, encoding="utf-8")
    (tmp_path / "lone.extracted.srt").write_text(SRT, encoding="utf-8")
    extract = _extract_to_disk(mocker)
    translate_file = mocker.patch("mkv_subtitle_translator.cli.OpenRouterTranslator.translate_file")

    result = runner.invoke(app, [str(tmp_path), "--force"])

    assert result.exit_code == 0
    extract.assert_called_once_with(str(tmp_path / "video.mkv"))
    assert _outputs(translate_file) == ["lone.et.srt", "video.et.srt"]


def test_folder_run_ignores_a_merge_that_never_finished(tmp_path, mocker):
    (tmp_path / "episode.mkv.temp.mkv").touch()
    extract = _extract_to_disk(mocker)
    translate_file = mocker.patch("mkv_subtitle_translator.cli.OpenRouterTranslator.translate_file")

    result = runner.invoke(app, [str(tmp_path)])

    assert "No files to translate" in result.stdout
    extract.assert_not_called()
    translate_file.assert_not_called()


def test_folder_run_keeps_a_video_that_is_only_named_temp(tmp_path, mocker):
    (tmp_path / "making.of.temp.mkv").touch()
    extract = _extract_to_disk(mocker)
    mocker.patch("mkv_subtitle_translator.cli.OpenRouterTranslator.translate_file")

    runner.invoke(app, [str(tmp_path)])

    extract.assert_called_once_with(str(tmp_path / "making.of.temp.mkv"))


def test_folder_run_works_when_the_folder_name_has_brackets(tmp_path, mocker):
    folder = tmp_path / "Show [1080p]"
    folder.mkdir()
    (folder / "episode.mkv").touch()
    (folder / "lone.extracted.srt").write_text(SRT, encoding="utf-8")
    extract = _extract_to_disk(mocker)
    translate_file = mocker.patch("mkv_subtitle_translator.cli.OpenRouterTranslator.translate_file")

    runner.invoke(app, [str(folder)])

    extract.assert_called_once_with(str(folder / "episode.mkv"))
    assert _outputs(translate_file) == ["episode.et.srt", "lone.et.srt"]


def test_one_failed_video_does_not_stop_the_others(tmp_path, mocker):
    for name in ("a", "b", "c"):
        (tmp_path / f"{name}.mkv").touch()
        (tmp_path / f"{name}.extracted.srt").write_text(SRT, encoding="utf-8")

    def translate_file(subtitles, output, **kwargs):
        if output.endswith("b.et.srt"):
            raise TranslationFailed("1 of 1 subtitles were not translated")
        Path(output).write_text(SRT, encoding="utf-8")

    mocker.patch(
        "mkv_subtitle_translator.cli.OpenRouterTranslator.translate_file",
        side_effect=translate_file,
    )
    merge = mocker.patch("mkv_subtitle_translator.cli.merge_subtitles_into_mkv")

    result = runner.invoke(app, [str(tmp_path)])

    assert result.exit_code == 1
    assert sorted(Path(call.args[0]).name for call in merge.call_args_list) == ["a.mkv", "c.mkv"]
    assert "Not finished: b.extracted.srt" in result.stdout
    assert "ALL TRANSLATIONS COMPLETE" not in result.stdout


def test_a_failed_merge_is_not_reported_as_complete(tmp_path, mocker):
    (tmp_path / "show.mkv").touch()
    (tmp_path / "show.extracted.srt").write_text(SRT, encoding="utf-8")
    (tmp_path / "show.et.srt").write_text(SRT, encoding="utf-8")
    mocker.patch("mkv_subtitle_translator.cli.merge_subtitles_into_mkv", return_value=False)

    result = runner.invoke(app, [str(tmp_path)])

    assert result.exit_code == 1
    assert "Not finished: show.mkv" in result.stdout
    assert "ALL TRANSLATIONS COMPLETE" not in result.stdout
