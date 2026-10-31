from __future__ import annotations

import pytest

from mkv_subtitle_translator.backends import (
    API_CHUNK_SIZE,
    DEFAULT_BATCH_SIZE,
    QuotaExhausted,
)
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

    def test_keeps_the_source_lines_of_each_block(self, tmp_path):
        srt = tmp_path / "sample.srt"
        srt.write_text(SAMPLE_SRT, encoding="utf-8")
        translator = OpenRouterTranslator("dummy-key")
        subtitles = translator.read_srt(str(srt))
        assert [s.source_lines for s in subtitles] == [
            ("Hello there", "my old friend"),
            ("[door creaks]",),
            ("Nice to see you", "again today"),
        ]


class TestWriteSrt:
    def test_two_speaker_block_keeps_its_two_lines(self, tmp_path):
        translator = OpenRouterTranslator("dummy-key")
        sub = Subtitle(
            index="1",
            timestamp="00:00:01,000 --> 00:00:02,000",
            text="- Hello. - Hi.",
            translated_text="- Tere. - Hei.",
            source_lines=("- Hello.", "- Hi."),
        )
        out = tmp_path / "out.srt"
        translator.write_srt([sub], str(out))
        content = out.read_text(encoding="utf-8-sig")
        text_block = content.split("\n", 2)[2].rstrip("\n")
        assert text_block == "- Tere.\n- Hei."

    def test_leaves_single_line_blocks_alone(self, tmp_path):
        translator = OpenRouterTranslator("dummy-key")
        sub = Subtitle(
            index="1",
            timestamp="00:00:01,000 --> 00:00:02,000",
            text="[door creaks]",
            translated_text="[uks kriuksub]",
            source_lines=("[door creaks]",),
        )
        out = tmp_path / "out.srt"
        translator.write_srt([sub], str(out))
        content = out.read_text(encoding="utf-8-sig")
        text_block = content.split("\n", 2)[2].rstrip("\n")
        assert text_block == "[uks kriuksub]"

    def test_turns_curly_quotes_straight(self, tmp_path):
        translator = OpenRouterTranslator("dummy-key")
        sub = Subtitle(
            index="1",
            timestamp="00:00:01,000 --> 00:00:02,000",
            text="'Hi,' he said and 'left'.",
            translated_text="„Tere“ ütles ta ja “läks” ära.",
        )
        out = tmp_path / "out.srt"
        translator.write_srt([sub], str(out))
        content = out.read_text(encoding="utf-8-sig")
        assert content.split("\n", 2)[2].rstrip("\n") == '"Tere" ütles ta ja "läks" ära.'

    def test_output_is_utf8_with_bom(self, tmp_path):
        translator = OpenRouterTranslator("dummy-key")
        sub = Subtitle(
            index="1",
            timestamp="00:00:01,000 --> 00:00:02,000",
            text="Hi",
            translated_text="Tere",
        )
        out = tmp_path / "out.srt"
        translator.write_srt([sub], str(out))
        assert out.read_bytes().startswith(b"\xef\xbb\xbf")


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
    def test_announces_batch_before_waiting_for_translation(self, mocker, capsys):
        translator = OpenRouterTranslator("", "codex")
        subtitles = [Subtitle(index=str(i), timestamp="t", text="Hi") for i in (10, 20, 30)]
        snapshots = []

        def translate(*args, **kwargs):
            snapshots.append(capsys.readouterr().err)
            return "[10] Tere\n[20] Tere\n[30] Tere", 0, 0

        mocker.patch.object(translator.client, "translate", side_effect=translate)
        translator.translate_subtitles(subtitles, chunk_size=2)

        assert "Batch 1/2" in snapshots[0]
        assert "10-20" in snapshots[0]
        assert "2 subtitles" in snapshots[0]
        assert "GPT-6 Astra" in snapshots[0]
        assert "Batch 2/2" in snapshots[1]
        assert "30-30" in snapshots[1]
        assert all(sub.translated_text == "Tere" for sub in subtitles)

    def test_reports_partial_batches_without_claiming_all_translated(self, mocker, capsys):
        translator = OpenRouterTranslator("", "codex")
        subtitles = [Subtitle(index=str(i), timestamp="t", text="Hi") for i in (1, 2)]
        mocker.patch.object(translator.client, "translate", return_value=("[1] Tere", 0, 0))

        translator.translate_subtitles(subtitles)

        output = capsys.readouterr().err
        assert "2/2 processed" in output
        assert "1 translated, 1 failed" in output
        assert translator.stats.completed == 1
        assert translator.stats.failed == 1
        assert subtitles[1].translated_text == "Hi"

    def test_reports_batch_error_and_continues(self, mocker, capsys):
        translator = OpenRouterTranslator("", "codex")
        subtitles = [Subtitle(index=str(i), timestamp="t", text="Hi") for i in (1, 2)]
        mocker.patch.object(
            translator.client,
            "translate",
            side_effect=[RuntimeError("offline"), ("[2] Tere", 0, 0)],
        )

        translator.translate_subtitles(subtitles, chunk_size=1)

        output = capsys.readouterr().err
        assert "Batch 1/2" in output and "offline" in output
        assert "2/2 processed" in output
        assert "1 translated, 1 failed" in output
        assert subtitles[1].translated_text == "Tere"

    def test_empty_translation_is_reported_as_failed(self, mocker, capsys):
        translator = OpenRouterTranslator("", "codex")
        sub = Subtitle(index="1", timestamp="t", text="Hi")
        mocker.patch.object(translator.client, "translate", return_value=('[1] ""', 0, 0))

        translator.translate_subtitles([sub])

        assert "0 translated, 1 failed" in capsys.readouterr().err
        assert sub.translated_text == "Hi"
        assert translator.stats.completed == 0
        assert translator.stats.failed == 1

    def test_exhausted_chain_raises_instead_of_writing_english(self, mocker):
        translator = OpenRouterTranslator("", "codex")
        sub = Subtitle(index="1", timestamp="t1", text="Hi")
        mocker.patch.object(
            translator.client, "translate", side_effect=QuotaExhausted("all backends dry")
        )

        with pytest.raises(QuotaExhausted):
            translator.translate_subtitles([sub])

        assert sub.translated_text is None

    def test_each_batch_gets_english_neighbours_and_the_sheet(self, mocker):
        translator = OpenRouterTranslator("", "codex")
        subtitles = [Subtitle(index=str(i), timestamp="t", text=f"Line {i}") for i in range(1, 16)]
        translate = mocker.patch.object(
            translator.client, "translate", return_value=("[6] Rida", 0, 0)
        )

        translator.translate_subtitles(
            subtitles, chunk_size=5, source_name="show.srt", term_sheet="Code -> kood"
        )

        prompt = translate.call_args_list[1].args[1]
        assert "Term sheet:\nCode -> kood" in prompt
        assert (
            "earlier subtitles:\n[1] Line 1\n[2] Line 2\n[3] Line 3\n[4] Line 4\n[5] Line 5"
            in prompt
        )
        assert (
            "later subtitles:\n[11] Line 11\n[12] Line 12\n[13] Line 13\n[14] Line 14\n[15] Line 15"
            in prompt
        )

    def test_context_cue_returned_by_the_model_is_ignored(self, mocker):
        translator = OpenRouterTranslator("", "codex")
        subtitles = [Subtitle(index=str(i), timestamp="t", text="Hi") for i in (1, 2)]
        mocker.patch.object(
            translator.client,
            "translate",
            side_effect=[("[1] Üks\n[2] Vale", 0, 0), ("[2] Kaks", 0, 0)],
        )

        translator.translate_subtitles(subtitles, chunk_size=1)

        assert [s.translated_text for s in subtitles] == ["Üks", "Kaks"]
        assert translator.stats.completed == 2


class TestChunkSizeDefault:
    @pytest.mark.parametrize(
        ("model", "expected"), [("codex", DEFAULT_BATCH_SIZE), ("gpt-5.4", API_CHUNK_SIZE)]
    )
    def test_cli_backends_batch_bigger_than_the_api(self, mocker, model, expected):
        translator = OpenRouterTranslator("dummy-key", model)
        batch = mocker.patch.object(translator, "_batch_translate")

        translator.translate_subtitles([Subtitle(index="1", timestamp="t1", text="Hi")])

        assert batch.call_args.kwargs["batch_size"] == expected

    def test_explicit_chunk_size_wins(self, mocker):
        translator = OpenRouterTranslator("", "codex")
        batch = mocker.patch.object(translator, "_batch_translate")

        translator.translate_subtitles([Subtitle(index="1", timestamp="t1", text="Hi")], 25)

        assert batch.call_args.kwargs["batch_size"] == 25
