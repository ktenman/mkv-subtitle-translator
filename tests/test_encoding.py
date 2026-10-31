"""Whole runs in a subprocess, because locale and stdout encoding are set at start-up."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

FAKE_CODEX = r"""#!/bin/sh
while [ $# -gt 0 ]; do
    [ "$1" = -o ] && out="$2"
    shift
done
case "$(cat)" in
    *"subtitle reviser"*) printf '[1] Parandatud õ\n' > "$out" ;;
    *) printf '[1] Tere\n' > "$out" ;;
esac
"""

FAKE_CLAUDE = r"""#!/bin/sh
reply='[1] Tere'
for arg in "$@"; do
    case "$arg" in *"subtitle reviser"*) reply='[1] Parandatud õ' ;; esac
done
cat > /dev/null
printf '[{"is_error": false, "result": "%s"}]' "$reply"
"""

FAKE_FFPROBE = r"""#!/bin/sh
printf '{"streams": [{"tags": {"language": "eng", "title": "Õhtu"}}]}'
"""

FAKE_FFMPEG = r"""#!/bin/sh
for arg in "$@"; do out="$arg"; done
printf 'title: Õhtu\n' >&2
printf 'merged' > "$out"
"""

CLI = "import mkv_subtitle_translator.cli as cli; cli._check_and_upgrade = id; cli.main()"
MERGE = (
    "import sys; from mkv_subtitle_translator.mkv import merge_subtitles_into_mkv as merge; "
    "sys.exit(0 if merge(sys.argv[1], [sys.argv[2]], backup=False) else 1)"
)
ASCII_LOCALE = {"LC_ALL": "C", "PYTHONCOERCECLOCALE": "0", "PYTHONUTF8": "0"}


def _run(tmp_path, env, *args):
    fakes = tmp_path / "bin"
    fakes.mkdir()
    scripts = {
        "codex": FAKE_CODEX,
        "claude": FAKE_CLAUDE,
        "ffprobe": FAKE_FFPROBE,
        "ffmpeg": FAKE_FFMPEG,
    }
    for name, script in scripts.items():
        (fakes / name).write_text(script, encoding="utf-8")
        (fakes / name).chmod(0o755)
    path = f"{fakes}{os.pathsep}{os.environ['PATH']}"
    return subprocess.run(
        [sys.executable, "-c", *args],
        env={**os.environ, "PATH": path, **env},
        capture_output=True,
        timeout=60,
    )


def _translate(tmp_path, env, *args):
    srt = tmp_path / "show.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:02,000\nHi\n\n", encoding="utf-8")
    return _run(tmp_path, env, CLI, "-f", str(srt), *args)


@pytest.mark.parametrize("model", ["codex", "claude"])
def test_a_run_finishes_on_a_non_utf8_locale(tmp_path, model):
    result = _translate(tmp_path, ASCII_LOCALE, "--model", model)

    assert result.returncode == 0, result.stderr.decode()
    assert "Parandatud õ" in (tmp_path / "show.et.srt").read_text(encoding="utf-8-sig")


def test_a_non_utf8_stdout_keeps_the_corrections_and_finishes(tmp_path):
    result = _translate(tmp_path, {"PYTHONIOENCODING": "ascii"})

    assert result.returncode == 0, result.stderr.decode()
    assert "Parandatud õ" in (tmp_path / "show.et.srt").read_text(encoding="utf-8-sig")
    assert b"ALL TRANSLATIONS COMPLETE" in result.stdout


def test_a_merge_reads_ffmpeg_output_as_utf8_on_any_locale(tmp_path):
    video = tmp_path / "show.mkv"
    video.touch()
    subtitles = tmp_path / "show.et.srt"
    subtitles.touch()

    result = _run(
        tmp_path, {**ASCII_LOCALE, "PYTHONIOENCODING": "utf-8"}, MERGE, str(video), str(subtitles)
    )

    assert result.returncode == 0, result.stdout.decode()
    assert video.read_text(encoding="utf-8") == "merged"
