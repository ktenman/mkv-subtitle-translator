from __future__ import annotations

from mkv_subtitle_translator.linebreak import restore_line_break


class TestRestoreLineBreak:
    def test_leaves_already_multiline_text_unchanged(self):
        text = "line one\nline two"
        assert restore_line_break(text) == text

    def test_single_word_with_no_spaces_unchanged(self):
        assert restore_line_break("Word") == "Word"

    def test_splits_plain_sentence_near_midpoint(self):
        result = restore_line_break("Hello there, my old friend")
        assert result == "Hello there,\nmy old friend"

    def test_splits_two_speaker_dash_dialogue(self):
        result = restore_line_break("- Are you coming? - Not tonight.")
        assert result == "- Are you coming?\n- Not tonight."

    def test_preserves_leading_an8_tag(self):
        result = restore_line_break("{\\an8}Hello there, my old friend")
        assert result == "{\\an8}Hello there,\nmy old friend"

    def test_preserves_italic_wrapper(self):
        result = restore_line_break("<i>Hello there, my old friend</i>")
        assert result == "<i>Hello there,\nmy old friend</i>"
