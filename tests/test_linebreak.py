from __future__ import annotations

from mkv_subtitle_translator.linebreak import restore_line_break

LONG = "Ma ei tea, kas me jõuame täna õhtul koju tagasi"


class TestSpeakers:
    def test_splits_at_the_inner_dash(self):
        result = restore_line_break("- Kas tuled? - Täna mitte.", ("- Are you?", "- Not tonight."))
        assert result == "- Kas tuled?\n- Täna mitte."

    def test_keeps_italic_wrapper(self):
        source = ("<i>- Are you coming?", "- Not tonight.</i>")
        result = restore_line_break("<i>- Kas tuled? - Täna mitte.</i>", source)
        assert result == "<i>- Kas tuled?\n- Täna mitte.</i>"

    def test_looks_past_an8(self):
        source = ("{\\an8}- Are you coming?", "- Not tonight.")
        result = restore_line_break("{\\an8}- Kas tuled? - Täna mitte.", source)
        assert result == "{\\an8}- Kas tuled?\n- Täna mitte."

    def test_finds_a_dash_inside_an_italic_tag(self):
        source = ("- ♪ music", "<i>- Line two</i>")
        result = restore_line_break("- ♪ muusika <i>- Teine rida</i>", source)
        assert result == "- ♪ muusika\n<i>- Teine rida</i>"

    def test_each_speaker_in_own_italics(self):
        source = ("<i>- Are you coming?</i>", "<i>- Not tonight.</i>")
        result = restore_line_break("<i>- Kas tuled?</i> <i>- Täna mitte.</i>", source)
        assert result == "<i>- Kas tuled?</i>\n<i>- Täna mitte.</i>"

    def test_no_inner_dash_falls_through_to_the_length_rules(self):
        assert restore_line_break("Kas tuled?", ("- Are you?", "- No.")) == "Kas tuled?"


class TestLabel:
    def test_keeps_a_lone_label_on_line_one(self):
        source = ("[door creaks]", "Who's there?")
        result = restore_line_break("[uks kriuksub] Kes seal on?", source)
        assert result == "[uks kriuksub]\nKes seal on?"


class TestLength:
    def test_short_text_stays_on_one_line_even_from_a_two_line_source(self):
        text = "Tere, mu vana sõber"
        assert restore_line_break(text, ("Hello there,", "my old friend")) == text

    def test_splits_after_punctuation_when_over_the_limit(self):
        assert restore_line_break(LONG) == "Ma ei tea,\nkas me jõuame täna õhtul koju tagasi"

    def test_never_splits_between_two_capitalised_words(self):
        result = restore_line_break("Ma rääkisin eile õhtul pikalt Angel Bautista naisega kohvikus")
        assert result == "Ma rääkisin eile õhtul pikalt\nAngel Bautista naisega kohvikus"

    def test_moves_off_a_balanced_break_that_would_split_a_name(self):
        result = restore_line_break("Ma rääkisin eile õhtul Angel Bautista naisega kohvikus pikalt")
        assert result == "Ma rääkisin eile õhtul Angel Bautista\nnaisega kohvikus pikalt"

    def test_does_not_split_straight_after_a_function_word(self):
        result = restore_line_break("Ta läks poodi leiba ostma ja jäi sinna terveks õhtuks pidama")
        assert result == "Ta läks poodi leiba ostma ja jäi\nsinna terveks õhtuks pidama"

    def test_punctuation_never_beats_the_line_limit(self):
        result = restore_line_break(
            "Ma ei tea seda üldse, aga me jõuame täna õhtul kindlasti koju tagasi"
        )
        assert result == "Ma ei tea seda üldse, aga me jõuame\ntäna õhtul kindlasti koju tagasi"

    def test_text_too_long_for_two_lines_still_gets_two_lines_and_loses_nothing(self):
        text = " ".join(["üks"] * 30)
        result = restore_line_break(text)
        assert result.count("\n") == 1
        assert result.replace("\n", " ") == text

    def test_keeps_wrap_tags_outside_the_break(self):
        assert restore_line_break(f"{{\\an8}}{LONG}").startswith("{\\an8}Ma ei tea,\n")
        assert restore_line_break(f"<i>{LONG}</i>").endswith("koju tagasi</i>")

    def test_never_breaks_inside_a_tag(self):
        result = restore_line_break(f'<font color="#ffffff">{LONG}</font>')
        assert result == f'<font color="#ffffff">Ma ei tea,\n{LONG[11:]}</font>'

    def test_skips_a_tag_space_even_when_it_is_the_best_balance(self):
        tagged = f'{"a" * 30}<font color="#ffffff">{"b" * 20}</font>'
        assert restore_line_break(f"{tagged} ja") == f"{tagged}\nja"


def test_leaves_already_multiline_text_unchanged():
    assert restore_line_break("line one\nline two") == "line one\nline two"


def test_single_word_with_no_spaces_unchanged():
    assert restore_line_break("Word") == "Word"
