from __future__ import annotations

import itertools
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

from mkv_subtitle_translator.mkv import (
    extract_best_subtitle_from_mkv,
    extract_subtitle_from_mkv,
    get_mkv_subtitle_streams,
    merge_subtitles_into_mkv,
)


class TestGetMkvSubtitleStreams:
    def test_parses_ffprobe_json(self, mocker):
        streams = [{"index": 0, "tags": {"language": "eng"}}]
        mocker.patch(
            "mkv_subtitle_translator.mkv.subprocess.run",
            return_value=SimpleNamespace(stdout=json.dumps({"streams": streams}), returncode=0),
        )
        assert get_mkv_subtitle_streams("movie.mkv") == streams

    def test_returns_empty_list_on_called_process_error(self, mocker):
        mocker.patch(
            "mkv_subtitle_translator.mkv.subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "ffprobe"),
        )
        assert get_mkv_subtitle_streams("movie.mkv") == []

    def test_returns_empty_list_when_ffprobe_missing(self, mocker):
        mocker.patch("mkv_subtitle_translator.mkv.subprocess.run", side_effect=FileNotFoundError)
        assert get_mkv_subtitle_streams("movie.mkv") == []


class TestExtractSubtitleFromMkv:
    def test_builds_stream_mapped_command(self, mocker):
        run_mock = mocker.patch(
            "mkv_subtitle_translator.mkv.subprocess.run",
            return_value=SimpleNamespace(returncode=0),
        )
        assert extract_subtitle_from_mkv("movie.mkv", 2, "out.srt") is True
        cmd = run_mock.call_args[0][0]
        assert "0:s:2" in cmd

    def test_returns_false_on_failure(self, mocker):
        mocker.patch(
            "mkv_subtitle_translator.mkv.subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "ffmpeg"),
        )
        assert extract_subtitle_from_mkv("movie.mkv", 0, "out.srt") is False


def _tracks(mocker, *tracks):
    """Fake a video's subtitle tracks, each a (language tag or None, text) pair."""
    mocker.patch(
        "mkv_subtitle_translator.mkv.get_mkv_subtitle_streams",
        return_value=[{"tags": {"language": lang}} if lang else {} for lang, _ in tracks],
    )

    def extract(mkv_file, index, output):
        Path(output).write_text(tracks[index][1], encoding="utf-8")
        return True

    mocker.patch("mkv_subtitle_translator.mkv.extract_subtitle_from_mkv", side_effect=extract)


class TestExtractBestSubtitleFromMkv:
    def test_an_untagged_source_wins_over_a_longer_estonian_track(self, mocker, tmp_path):
        _tracks(mocker, (None, "Hello"), ("est", "Tere tulemast koju, sõber"))

        extracted = extract_best_subtitle_from_mkv(str(tmp_path / "movie.mkv"))

        assert Path(extracted).read_text(encoding="utf-8") == "Hello"

    def test_a_video_with_only_estonian_has_nothing_to_translate(self, mocker, tmp_path):
        _tracks(mocker, ("est", "Tere"))

        assert extract_best_subtitle_from_mkv(str(tmp_path / "movie.mkv")) is None


class TestMergeSubtitlesIntoMkv:
    def test_replaces_existing_estonian_stream(self, mocker):
        mocker.patch(
            "mkv_subtitle_translator.mkv.get_mkv_subtitle_streams",
            return_value=[
                {"tags": {"language": "eng"}},
                {"tags": {"language": "est"}},
            ],
        )
        run_mock = mocker.patch(
            "mkv_subtitle_translator.mkv.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stderr=""),
        )
        mocker.patch("mkv_subtitle_translator.mkv.os.path.exists", return_value=False)
        rename_mock = mocker.patch("mkv_subtitle_translator.mkv.os.rename")
        replace_mock = mocker.patch("mkv_subtitle_translator.mkv.os.replace")

        result = merge_subtitles_into_mkv("movie.mkv", ["movie.et.srt"], backup=True)

        assert result is True
        cmd = run_mock.call_args[0][0]
        assert "0:s:0" in cmd
        assert "0:s:1" not in cmd
        rename_mock.assert_called_once_with("movie.mkv", "movie.mkv.backup")
        replace_mock.assert_called_once_with("movie.mkv.temp.mkv", "movie.mkv")

    def test_second_merge_keeps_the_original_in_the_backup(self, mocker, tmp_path):
        video = tmp_path / "movie.mkv"
        video.write_text("original")
        merges = itertools.count(1)

        def ffmpeg(cmd, **kwargs):
            Path(cmd[-1]).write_text(f"merge {next(merges)}")
            return SimpleNamespace(returncode=0, stderr="")

        mocker.patch("mkv_subtitle_translator.mkv.get_mkv_subtitle_streams", return_value=[])
        mocker.patch("mkv_subtitle_translator.mkv.subprocess.run", side_effect=ffmpeg)

        assert merge_subtitles_into_mkv(str(video), ["movie.et.srt"]) is True
        assert merge_subtitles_into_mkv(str(video), ["movie.et.srt"]) is True

        assert video.read_text() == "merge 2"
        assert (tmp_path / "movie.mkv.backup").read_text() == "original"

    def test_returns_false_when_ffmpeg_fails(self, mocker):
        mocker.patch("mkv_subtitle_translator.mkv.get_mkv_subtitle_streams", return_value=[])
        mocker.patch(
            "mkv_subtitle_translator.mkv.subprocess.run",
            return_value=SimpleNamespace(returncode=1, stderr="boom"),
        )
        result = merge_subtitles_into_mkv("movie.mkv", ["movie.et.srt"], backup=True)
        assert result is False
