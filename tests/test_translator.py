from __future__ import annotations

import re
import threading
import time

import pytest

from mkv_subtitle_translator.backends import (
    API_CHUNK_SIZE,
    DEFAULT_BATCH_SIZE,
    QuotaExhausted,
)
from mkv_subtitle_translator.models import Subtitle
from mkv_subtitle_translator.prompts import (
    BATCH_SYSTEM_PROMPT,
    CHECK_SYSTEM_PROMPT,
    TERM_SHEET_SYSTEM_PROMPT,
)
from mkv_subtitle_translator.translator import (
    OpenRouterTranslator,
    deduplicate_subtitles,
    read_reference,
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
    @pytest.fixture(autouse=True)
    def _one_call_at_a_time(self, mocker):
        mocker.patch("mkv_subtitle_translator.translator.CLI_WORKERS", 1)

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


class TestParallelBatches:
    def test_runs_five_calls_at_once_on_a_cli_backend(self, mocker):
        translator = OpenRouterTranslator("", "codex")
        subtitles = [Subtitle(index=str(i), timestamp="t", text="Hi") for i in range(1, 6)]
        barrier = threading.Barrier(5)

        def translate(system, user, **kwargs):
            barrier.wait(timeout=5)  # breaks unless all five are in flight together
            return "\n".join(f"[{i}] Tere" for i in range(1, 6)), 0, 0

        mocker.patch.object(translator.client, "translate", side_effect=translate)
        translator.translate_subtitles(subtitles, chunk_size=1)

        assert translator.stats.completed == 5

    def test_calls_the_api_one_at_a_time(self, mocker):
        translator = OpenRouterTranslator("dummy-key", "gpt-5.4")
        subtitles = [Subtitle(index=str(i), timestamp="t", text="Hi") for i in range(1, 4)]
        lock = threading.Lock()
        running = peak = 0

        def translate(system, user, **kwargs):
            nonlocal running, peak
            with lock:
                running += 1
                peak = max(peak, running)
            time.sleep(0.02)
            with lock:
                running -= 1
            return "\n".join(f"[{i}] Tere" for i in range(1, 4)), 1, 1

        mocker.patch.object(translator.client, "translate", side_effect=translate)
        translator.translate_subtitles(subtitles, chunk_size=1)

        assert peak == 1
        assert translator.stats.input_tokens == 3

    def test_each_batch_keeps_its_own_text_when_a_later_batch_finishes_first(self, mocker):
        translator = OpenRouterTranslator("", "codex")
        subtitles = [Subtitle(index=str(i), timestamp="t", text=f"Line {i}") for i in (1, 2)]
        second_done = threading.Event()

        def translate(system, user, **kwargs):
            if "Estonian translation.\n\n[2] Line 2" in user:
                second_done.set()
                return "[2] Kaks", 0, 0
            assert second_done.wait(5)
            return "[1] Üks", 0, 0

        mocker.patch.object(translator.client, "translate", side_effect=translate)
        translator.translate_subtitles(subtitles, chunk_size=1)

        assert [s.translated_text for s in subtitles] == ["Üks", "Kaks"]

    @pytest.mark.parametrize("error", [QuotaExhausted("dry"), KeyboardInterrupt()])
    def test_a_stop_cancels_calls_not_yet_started(self, mocker, error):
        translator = OpenRouterTranslator("", "codex")
        subtitles = [Subtitle(index=str(i), timestamp="t", text="Hi") for i in range(1, 13)]
        first = threading.Lock()

        def translate(system, user, **kwargs):
            if first.acquire(blocking=False):
                raise error
            time.sleep(0.05)
            return "", 0, 0

        translate_mock = mocker.patch.object(translator.client, "translate", side_effect=translate)

        with pytest.raises(type(error)):
            translator.translate_subtitles(subtitles, chunk_size=1)

        assert translate_mock.call_count < 12


def _backend(sheet="Code -> kood", check="NONE", tokens=(0, 0)):
    """Answer each stage's prompt. A stage is a reply, a function of the prompt or an exception."""

    def answer(stage, user):
        if isinstance(stage, BaseException):
            raise stage
        return (stage(user) if callable(stage) else stage, *tokens)

    def translate(system, user, **kwargs):
        if system == TERM_SHEET_SYSTEM_PROMPT:
            return answer(sheet, user)
        if system == CHECK_SYSTEM_PROMPT:
            return answer(check, user)
        block = user.split("Estonian translation.\n\n")[1].split("\n\nContext only")[0]
        numbers = re.findall(r"^\[(\d+)\]", block, re.M)
        return ("\n".join(f"[{n}] Tere" for n in numbers), *tokens)

    return translate


def _cues(count=3):
    return [Subtitle(index=str(i), timestamp="t", text=f"Line {i}") for i in range(1, count + 1)]


class TestTermSheet:
    def test_is_saved_and_reaches_every_batch(self, mocker, tmp_path):
        translator = OpenRouterTranslator("", "codex")
        translate = mocker.patch.object(translator.client, "translate", side_effect=_backend())
        out = tmp_path / "show.et.srt"

        translator.translate_file(_cues(), str(out), source_name="show.srt", chunk_size=1)

        assert (tmp_path / "show.et.terms.md").read_text(encoding="utf-8").strip() == "Code -> kood"
        calls = translate.call_args_list
        batch_prompts = [c.args[1] for c in calls if c.args[0] == BATCH_SYSTEM_PROMPT]
        assert len(batch_prompts) == 3
        assert all("Term sheet:\nCode -> kood" in prompt for prompt in batch_prompts)
        assert out.exists()

    def test_call_reads_the_whole_source_at_high_effort(self, mocker, tmp_path):
        translator = OpenRouterTranslator("", "codex", "max")
        translate = mocker.patch.object(translator.client, "translate", side_effect=_backend())

        translator.translate_file(_cues(), str(tmp_path / "show.et.srt"), source_name="show.srt")

        sheet_call = translate.call_args_list[0]
        assert "Source file: show.srt" in sheet_call.args[1]
        assert "[1] Line 1\n[2] Line 2\n[3] Line 3" in sheet_call.args[1]
        assert sheet_call.kwargs["effort"] == "high"
        assert sheet_call.kwargs["max_tokens"] == 8000
        assert "effort" not in translate.call_args_list[1].kwargs

    def test_existing_sheet_is_reused_and_named(self, mocker, tmp_path, capsys):
        translator = OpenRouterTranslator("", "codex")
        (tmp_path / "show.et.terms.md").write_text("Code -> seadus\n", encoding="utf-8")
        translate = mocker.patch.object(translator.client, "translate", side_effect=_backend())

        translator.translate_file(_cues(1), str(tmp_path / "show.et.srt"), source_name="show.srt")

        assert all(c.args[0] != TERM_SHEET_SYSTEM_PROMPT for c in translate.call_args_list)
        assert "Term sheet:\nCode -> seadus" in translate.call_args.args[1]
        assert "Reusing term sheet" in capsys.readouterr().out

    def test_failed_call_warns_and_continues_without_a_sheet(self, mocker, tmp_path, capsys):
        translator = OpenRouterTranslator("", "codex")
        translate = mocker.patch.object(
            translator.client, "translate", side_effect=_backend(RuntimeError("offline"))
        )
        out = tmp_path / "show.et.srt"

        translator.translate_file(_cues(1), str(out), source_name="show.srt")

        assert "Term sheet:" not in translate.call_args.args[1]
        assert "continuing without" in capsys.readouterr().out
        assert out.exists()
        assert not (tmp_path / "show.et.terms.md").exists()

    def test_quota_raises_and_writes_nothing(self, mocker, tmp_path):
        translator = OpenRouterTranslator("", "codex")
        mocker.patch.object(
            translator.client, "translate", side_effect=_backend(QuotaExhausted("dry"))
        )
        out = tmp_path / "show.et.srt"

        with pytest.raises(QuotaExhausted):
            translator.translate_file(_cues(1), str(out), source_name="show.srt")

        assert not out.exists()

    def test_per_line_models_get_no_sheet(self, mocker, tmp_path):
        translator = OpenRouterTranslator("dummy-key", "gpt-5.4-pro")
        translate = mocker.patch.object(translator.client, "translate", return_value=("Tere", 1, 1))
        out = tmp_path / "show.et.srt"

        translator.translate_file(_cues(1), str(out), source_name="show.srt")

        assert translate.call_count == 1
        assert not (tmp_path / "show.et.terms.md").exists()
        assert "Tere" in out.read_text(encoding="utf-8-sig")

    def test_no_cues_makes_no_call_and_writes_an_empty_file(self, mocker, tmp_path):
        translator = OpenRouterTranslator("", "codex")
        translate = mocker.patch.object(translator.client, "translate")
        out = tmp_path / "show.et.srt"

        translator.translate_file([], str(out), source_name="show.srt")

        translate.assert_not_called()
        assert out.read_bytes() == b""

    def test_stats_cover_the_sheet_and_start_fresh_for_each_file(self, mocker, tmp_path):
        translator = OpenRouterTranslator("dummy-key", "gpt-5.4")
        mocker.patch.object(translator.client, "translate", side_effect=_backend(tokens=(10, 1)))

        for name in ("one", "two"):
            translator.translate_file(
                _cues(1), str(tmp_path / f"{name}.et.srt"), source_name=f"{name}.srt"
            )

        assert translator.stats.input_tokens == 30
        assert translator.stats.total_subtitles == 1


class TestReference:
    def test_reads_windows_1252_and_drops_numbers_and_timing(self, tmp_path):
        path = tmp_path / "old.srt"
        path.write_bytes(
            "1\r\n00:00:01,000 --> 00:00:02,000\r\nTüdruk šokolaad\r\n".encode("cp1252")
        )
        assert read_reference(str(path)) == "Tüdruk šokolaad"

    def test_reads_utf8_with_bom(self, tmp_path):
        path = tmp_path / "old.srt"
        path.write_text("1\n00:00:01,000 --> 00:00:02,000\nTüdruk\n", encoding="utf-8-sig")
        assert read_reference(str(path)) == "Tüdruk"

    def test_an_undefined_byte_does_not_stop_the_run(self, tmp_path):
        path = tmp_path / "old.srt"
        path.write_bytes(b"T\xfcdruk \x81")
        assert read_reference(str(path)).startswith("Tüdruk")

    def test_reaches_only_the_sheet_prompt(self, mocker, tmp_path):
        reference = tmp_path / "old.srt"
        reference.write_text("Tume Reisija", encoding="utf-8")
        translator = OpenRouterTranslator("", "codex")
        translate = mocker.patch.object(translator.client, "translate", side_effect=_backend())

        translator.translate_file(
            _cues(1),
            str(tmp_path / "show.et.srt"),
            source_name="show.srt",
            references=[str(reference)],
        )

        first, *rest = [c.args[1] for c in translate.call_args_list]
        assert "Earlier Estonian subtitles" in first and "Tume Reisija" in first
        assert rest and all("Tume Reisija" not in prompt for prompt in rest)

    def test_is_not_read_when_a_sheet_exists_and_the_run_says_so(self, mocker, tmp_path, capsys):
        (tmp_path / "show.et.terms.md").write_text("Code -> kood\n", encoding="utf-8")
        translator = OpenRouterTranslator("", "codex")
        mocker.patch.object(translator.client, "translate", side_effect=_backend())

        translator.translate_file(
            _cues(1),
            str(tmp_path / "show.et.srt"),
            source_name="show.srt",
            references=[str(tmp_path / "gone.srt")],
        )

        assert "not read" in capsys.readouterr().out

    def test_per_line_models_say_it_was_ignored(self, mocker, tmp_path, capsys):
        translator = OpenRouterTranslator("dummy-key", "gpt-5.4-pro")
        mocker.patch.object(translator.client, "translate", return_value=("Tere", 1, 1))

        translator.translate_file(
            _cues(1),
            str(tmp_path / "show.et.srt"),
            source_name="show.srt",
            references=[str(tmp_path / "old.srt")],
        )

        assert "--reference" in capsys.readouterr().out


class TestErrorCheck:
    def test_corrections_reach_the_final_file(self, mocker, tmp_path, capsys):
        translator = OpenRouterTranslator("", "codex")
        mocker.patch.object(
            translator.client, "translate", side_effect=_backend(check="[2] Parandatud")
        )
        out = tmp_path / "show.et.srt"

        translator.translate_file(_cues(), str(out), source_name="show.srt")

        assert "Parandatud" in out.read_text(encoding="utf-8-sig")
        output = capsys.readouterr().out
        assert "#2" in output and "Tere" in output and "Parandatud" in output

    def test_none_changes_nothing_and_writes_once(self, mocker, tmp_path):
        translator = OpenRouterTranslator("", "codex")
        mocker.patch.object(translator.client, "translate", side_effect=_backend())
        write = mocker.spy(translator, "write_srt")

        translator.translate_file(_cues(), str(tmp_path / "show.et.srt"), source_name="show.srt")

        assert write.call_count == 1

    def test_same_text_is_not_a_correction(self, mocker, tmp_path):
        translator = OpenRouterTranslator("", "codex")
        mocker.patch.object(translator.client, "translate", side_effect=_backend(check="[2] Tere"))
        write = mocker.spy(translator, "write_srt")

        translator.translate_file(_cues(), str(tmp_path / "show.et.srt"), source_name="show.srt")

        assert write.call_count == 1

    def test_cue_outside_the_batch_is_not_applied(self, mocker, tmp_path):
        translator = OpenRouterTranslator("", "codex")
        replies = {"[1] to [1]": "[2] Vale", "[2] to [2]": "NONE", "[3] to [3]": "NONE"}

        def check(user):
            return next(reply for key, reply in replies.items() if key in user)

        mocker.patch.object(translator.client, "translate", side_effect=_backend(check=check))
        out = tmp_path / "show.et.srt"

        translator.translate_file(_cues(), str(out), source_name="show.srt", chunk_size=1)

        assert "Vale" not in out.read_text(encoding="utf-8-sig")

    def test_output_exists_before_the_first_check_call(self, mocker, tmp_path):
        translator = OpenRouterTranslator("", "codex")
        out = tmp_path / "show.et.srt"
        seen = []

        def check(user):
            seen.append(out.exists())
            return "NONE"

        mocker.patch.object(translator.client, "translate", side_effect=_backend(check=check))
        translator.translate_file(_cues(), str(out), source_name="show.srt")

        assert seen == [True]

    def test_batch_error_keeps_that_batch_and_is_counted(self, mocker, tmp_path, capsys):
        translator = OpenRouterTranslator("", "codex")

        def check(user):
            if "[1] to [1]" in user:
                raise RuntimeError("offline")
            return "[2] Parandatud" if "[2] to [2]" in user else "NONE"

        mocker.patch.object(translator.client, "translate", side_effect=_backend(check=check))
        out = tmp_path / "show.et.srt"

        translator.translate_file(_cues(), str(out), source_name="show.srt", chunk_size=1)

        assert "Parandatud" in out.read_text(encoding="utf-8-sig")
        assert "1 of 3 batches could not be checked" in capsys.readouterr().out

    def test_quota_stops_the_check_and_keeps_the_output(self, mocker, tmp_path, capsys):
        translator = OpenRouterTranslator("", "codex")
        mocker.patch.object(
            translator.client, "translate", side_effect=_backend(check=QuotaExhausted("dry"))
        )
        out = tmp_path / "show.et.srt"

        translator.translate_file(_cues(), str(out), source_name="show.srt")

        assert "Tere" in out.read_text(encoding="utf-8-sig")
        assert "could not be checked" in capsys.readouterr().out

    def test_sheet_reaches_the_check_and_stats_include_it(self, mocker, tmp_path):
        translator = OpenRouterTranslator("dummy-key", "gpt-5.4")
        translate = mocker.patch.object(
            translator.client, "translate", side_effect=_backend(tokens=(10, 1))
        )

        translator.translate_file(_cues(1), str(tmp_path / "show.et.srt"), source_name="show.srt")

        assert "Term sheet:\nCode -> kood" in translate.call_args.args[1]
        assert translate.call_count == 3
        assert translator.stats.input_tokens == 30

    def test_every_check_call_reads_the_whole_title(self, mocker, tmp_path):
        translator = OpenRouterTranslator("", "codex")
        translate = mocker.patch.object(translator.client, "translate", side_effect=_backend())

        translator.translate_file(
            _cues(), str(tmp_path / "show.et.srt"), source_name="show.srt", chunk_size=1
        )

        checks = [c.args[1] for c in translate.call_args_list if c.args[0] == CHECK_SYSTEM_PROMPT]
        assert len(checks) == 3
        assert all("[1] Line 1\n[2] Line 2\n[3] Line 3" in prompt for prompt in checks)

    def test_per_line_models_get_no_check(self, mocker, tmp_path):
        translator = OpenRouterTranslator("dummy-key", "gpt-5.4-pro")
        translate = mocker.patch.object(translator.client, "translate", return_value=("Tere", 1, 1))

        translator.translate_file(_cues(1), str(tmp_path / "show.et.srt"), source_name="show.srt")

        assert translate.call_count == 1


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
