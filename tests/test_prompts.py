from __future__ import annotations

from mkv_subtitle_translator.models import Subtitle
from mkv_subtitle_translator.prompts import BATCH_SYSTEM_PROMPT, batch_prompt, check_prompt


def _subs(*numbers):
    return [Subtitle(index=str(n), timestamp="t", text=f"Line {n}") for n in numbers]


def test_keeps_the_ten_rules_and_adds_two():
    assert (
        "10. Preserve any formatting (italics, dashes for speaker changes)" in BATCH_SYSTEM_PROMPT
    )
    assert "11. Use the names, terms and sina or teie from the term sheet." in BATCH_SYSTEM_PROMPT
    assert '12. Lines under "Context only" are for understanding.' in BATCH_SYSTEM_PROMPT


def test_has_no_layout_rules():
    assert "42" not in BATCH_SYSTEM_PROMPT
    assert "line break" not in BATCH_SYSTEM_PROMPT.lower()


def test_orders_sheet_context_and_batch():
    prompt = batch_prompt("show.srt", "Code -> kood", _subs(1), _subs(2, 3), _subs(4))
    assert prompt == (
        "Source file: show.srt\n\n"
        "Term sheet:\nCode -> kood\n\n"
        "Context only, earlier subtitles:\n[1] Line 1\n\n"
        "Translate all 2 subtitles below to Estonian. "
        "Return each line as [number] Estonian translation.\n\n[2] Line 2\n[3] Line 3\n\n"
        "Context only, later subtitles:\n[4] Line 4"
    )


def test_leaves_out_empty_sections():
    prompt = batch_prompt("show.srt", "", [], _subs(1), [])
    assert "Term sheet" not in prompt
    assert "Context only" not in prompt


def test_check_prompt_carries_the_whole_title_and_the_range():
    subs = _subs(1, 2, 3)
    for sub in subs:
        sub.translated_text = f"Rida {sub.index}"

    prompt = check_prompt("show.srt", "Code -> kood", subs, subs[1:2])

    assert "Term sheet:\nCode -> kood" in prompt
    assert "Complete English source:\n[1] Line 1\n[2] Line 2\n[3] Line 3" in prompt
    assert "Complete Estonian translation:\n[1] Rida 1\n[2] Rida 2\n[3] Rida 3" in prompt
    assert "Check subtitles [2] to [2]." in prompt
    assert "If none need correcting, return NONE." in prompt
