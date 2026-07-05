from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

from translate_subs_openrouter.mkv import (
    extract_subtitle_from_mkv,
    get_mkv_subtitle_streams,
    merge_subtitles_into_mkv,
)


class TestGetMkvSubtitleStreams:
    def test_parses_ffprobe_json(self, mocker):
        streams = [{"index": 0, "tags": {"language": "eng"}}]
        mocker.patch(
            "translate_subs_openrouter.mkv.subprocess.run",
            return_value=SimpleNamespace(stdout=json.dumps({"streams": streams}), returncode=0),
        )
        assert get_mkv_subtitle_streams("movie.mkv") == streams

    def test_returns_empty_list_on_called_process_error(self, mocker):
        mocker.patch(
            "translate_subs_openrouter.mkv.subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "ffprobe"),
        )
        assert get_mkv_subtitle_streams("movie.mkv") == []

    def test_returns_empty_list_when_ffprobe_missing(self, mocker):
        mocker.patch("translate_subs_openrouter.mkv.subprocess.run", side_effect=FileNotFoundError)
        assert get_mkv_subtitle_streams("movie.mkv") == []


class TestExtractSubtitleFromMkv:
    def test_builds_stream_mapped_command(self, mocker):
        run_mock = mocker.patch(
            "translate_subs_openrouter.mkv.subprocess.run",
            return_value=SimpleNamespace(returncode=0),
        )
        assert extract_subtitle_from_mkv("movie.mkv", 2, "out.srt") is True
        cmd = run_mock.call_args[0][0]
        assert "0:s:2" in cmd

    def test_returns_false_on_failure(self, mocker):
        mocker.patch(
            "translate_subs_openrouter.mkv.subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "ffmpeg"),
        )
        assert extract_subtitle_from_mkv("movie.mkv", 0, "out.srt") is False


class TestMergeSubtitlesIntoMkv:
    def test_replaces_existing_estonian_stream(self, mocker):
        mocker.patch(
            "translate_subs_openrouter.mkv.get_mkv_subtitle_streams",
            return_value=[
                {"tags": {"language": "eng"}},
                {"tags": {"language": "est"}},
            ],
        )
        run_mock = mocker.patch(
            "translate_subs_openrouter.mkv.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stderr=""),
        )
        mocker.patch("translate_subs_openrouter.mkv.os.path.exists", return_value=False)
        rename_mock = mocker.patch("translate_subs_openrouter.mkv.os.rename")

        result = merge_subtitles_into_mkv("movie.mkv", ["movie.et.srt"], backup=True)

        assert result is True
        cmd = run_mock.call_args[0][0]
        assert "0:s:0" in cmd
        assert "0:s:1" not in cmd
        assert rename_mock.call_count == 2

    def test_returns_false_when_ffmpeg_fails(self, mocker):
        mocker.patch("translate_subs_openrouter.mkv.get_mkv_subtitle_streams", return_value=[])
        mocker.patch(
            "translate_subs_openrouter.mkv.subprocess.run",
            return_value=SimpleNamespace(returncode=1, stderr="boom"),
        )
        result = merge_subtitles_into_mkv("movie.mkv", ["movie.et.srt"], backup=True)
        assert result is False
