from __future__ import annotations

import pytest

from mkv_subtitle_translator.backends import QuotaExhausted
from mkv_subtitle_translator.models import Subtitle
from mkv_subtitle_translator.translator import (
    OpenRouterTranslator,
    deduplicate_subtitles,
    strip_wrapping_quotes,
)

SAMPLE_SRT = """1
00:00:01,000 --> 00:00:02,000
Hello there
my old friend

2
00:00:03,000 --> 00:00:04,000
[door creaks]

3
00:00:05,000 --> 00:00:06,000
Nice to see you
again today
"""


class TestReadSrt:
    def test_joins_multiline_blocks_into_single_text(self, tmp_path):
        srt = tmp_path / "sample.srt"
        srt.write_text(SAMPLE_SRT, encoding="utf-8")
        translator = OpenRouterTranslator("dummy-key")
        subtitles = translator.read_srt(str(srt))
        assert subtitles[0].text == "Hello there my old friend"

    def test_tracks_line_count_per_block(self, tmp_path):
        srt = tmp_path / "sample.srt"
        srt.write_text(SAMPLE_SRT, encoding="utf-8")
        translator = OpenRouterTranslator("dummy-key")
        subtitles = translator.read_srt(str(srt))
        assert [s.line_count for s in subtitles] == [2, 1, 2]


class TestWriteSrt:
    def test_restores_two_line_blocks(self, tmp_path):
        translator = OpenRouterTranslator("dummy-key")
        sub = Subtitle(
            index="1",
            timestamp="00:00:01,000 --> 00:00:02,000",
            text="Hello there my old friend",
            translated_text="Tere seal mu vana sober",
            line_count=2,
        )
        out = tmp_path / "out.srt"
        translator.write_srt([sub], str(out))
        content = out.read_text(encoding="utf-8-sig")
        text_block = content.split("\n", 2)[2].rstrip("\n")
        assert "\n" in text_block

    def test_leaves_single_line_blocks_alone(self, tmp_path):
        translator = OpenRouterTranslator("dummy-key")
        sub = Subtitle(
            index="1",
            timestamp="00:00:01,000 --> 00:00:02,000",
            text="[door creaks]",
            translated_text="[uks kriuksub]",
            line_count=1,
        )
        out = tmp_path / "out.srt"
        translator.write_srt([sub], str(out))
        content = out.read_text(encoding="utf-8-sig")
        text_block = content.split("\n", 2)[2].rstrip("\n")
        assert text_block == "[uks kriuksub]"


class TestStripWrappingQuotes:
    def test_strips_estonian_quotes_codex_likes_to_add(self):
        assert strip_wrapping_quotes("„Tere, kullake.“") == "Tere, kullake."

    def test_strips_straight_quotes(self):
        assert strip_wrapping_quotes('"Tere"') == "Tere"

    def test_keeps_quotes_inside_the_line(self):
        assert strip_wrapping_quotes('"Ma tulen," ütles ta.') == '"Ma tulen," ütles ta.'

    def test_leaves_unquoted_text_alone(self):
        assert strip_wrapping_quotes("Tere") == "Tere"


class TestDeduplicateSubtitles:
    def test_removes_exact_duplicates(self):
        a = Subtitle(index="1", timestamp="t1", text="Hi")
        b = Subtitle(index="2", timestamp="t1", text="Hi")
        c = Subtitle(index="3", timestamp="t2", text="Bye")
        result = deduplicate_subtitles([a, b, c])
        assert [s.index for s in result] == ["1", "3"]


class TestTranslateChunk:
    def test_cache_hit_skips_client_call(self, mocker):
        translator = OpenRouterTranslator("dummy-key")
        sub = Subtitle(index="1", timestamp="t1", text="Hi")
        translator.translation_cache["Hi"] = "Tere"
        translate_mock = mocker.patch.object(translator.client, "translate")

        translator.translate_chunk([sub], [sub])

        assert sub.translated_text == "Tere"
        assert translator.stats.cached == 1
        translate_mock.assert_not_called()

    def test_cache_miss_calls_client_and_caches_result(self, mocker):
        translator = OpenRouterTranslator("dummy-key")
        sub = Subtitle(index="1", timestamp="t1", text="Hi")
        translate_mock = mocker.patch.object(
            translator.client, "translate", return_value=("Tere", 10, 5)
        )

        translator.translate_chunk([sub], [sub])

        assert sub.translated_text == "Tere"
        translate_mock.assert_called_once()
        assert translator.translation_cache["Hi"] == "Tere"


class TestBatchTranslate:
    def test_exhausted_chain_raises_instead_of_writing_english(self, mocker):
        translator = OpenRouterTranslator("", "codex")
        sub = Subtitle(index="1", timestamp="t1", text="Hi")
        mocker.patch.object(
            translator.client, "translate", side_effect=QuotaExhausted("all backends dry")
        )

        with pytest.raises(QuotaExhausted):
            translator.translate_subtitles([sub], chunk_size=200)

        assert sub.translated_text is None
