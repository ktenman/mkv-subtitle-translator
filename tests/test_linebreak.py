from __future__ import annotations

import pytest

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

    def test_looks_past_an8_on_the_second_line(self):
        source = ("{\\an8}- Are you coming?", "{\\an8}- Not tonight.")
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

    def test_splits_a_dash_with_no_space_after_it(self):
        result = restore_line_break("-Kas tuled? -Täna mitte.", ("-Are you?", "-Not tonight."))
        assert result == "-Kas tuled?\n-Täna mitte."

    def test_splits_when_only_the_second_line_has_a_dash(self):
        result = restore_line_break("Kas tuled? - Täna mitte.", ("Are you?", "- Not tonight."))
        assert result == "Kas tuled?\n- Täna mitte."

    def test_looks_past_a_font_tag(self):
        source = ('<font color="#ffffff">- Are you?</font>', '<font color="#ffffff">- No.</font>')
        result = restore_line_break(
            '<font color="#ffffff">- Kas tuled?</font> <font color="#ffffff">- Ei.</font>', source
        )
        assert result == (
            '<font color="#ffffff">- Kas tuled?</font>\n<font color="#ffffff">- Ei.</font>'
        )

    def test_a_double_dash_is_not_a_speaker(self):
        source = ("-I was just --", "-Not tonight.")
        result = restore_line_break("-Ma just -- -Täna mitte.", source)
        assert result == "-Ma just --\n-Täna mitte."

    def test_a_negative_number_is_not_a_speaker(self):
        source = ("-It is -5 today.", "-Cold.")
        result = restore_line_break("-Täna on -5 kraadi. -Külm.", source)
        assert result == "-Täna on -5 kraadi.\n-Külm."

    def test_a_spaced_hyphen_in_the_first_turn_is_not_the_second_speaker(self):
        source = ("- I was, how to say, tired.", "- Not tonight.")
        result = restore_line_break("- Ma olin - kuidas öelda - väsinud. - Täna mitte.", source)
        assert result == "- Ma olin - kuidas öelda - väsinud.\n- Täna mitte."

    def test_a_first_turn_can_end_in_a_quote(self):
        source = ('- She said, how to say, "no."', "- Fine.")
        result = restore_line_break('- Ta ütles - kuidas öelda - "ei." - Hästi.', source)
        assert result == '- Ta ütles - kuidas öelda - "ei."\n- Hästi.'

    def test_with_no_finished_sentence_the_first_dash_splits(self):
        source = ("- Are you", "- Not tonight.")
        result = restore_line_break("- Kas tuled - Täna mitte - Hästi", source)
        assert result == "- Kas tuled\n- Täna mitte - Hästi"


class TestLabel:
    def test_keeps_a_lone_label_on_line_one(self):
        source = ("[door creaks]", "Who's there?")
        result = restore_line_break("[uks kriuksub] Kes seal on?", source)
        assert result == "[uks kriuksub]\nKes seal on?"

    @pytest.mark.parametrize(
        ("source", "text", "expected"),
        [
            (
                ("{\\an8}[door creaks]", "Who's there?"),
                "{\\an8}[uks kriuksub] Kes seal on?",
                "{\\an8}[uks kriuksub]\nKes seal on?",
            ),
            (
                ("<i>[door creaks]</i>", "Who's there?"),
                "<i>[uks kriuksub]</i> Kes seal on?",
                "<i>[uks kriuksub]</i>\nKes seal on?",
            ),
            (
                ("<i>[door creaks]", "Who's there?</i>"),
                "<i>[uks kriuksub] Kes seal on?</i>",
                "<i>[uks kriuksub]\nKes seal on?</i>",
            ),
            (
                ("<i>[door creaks]</i>", "<i>Who's there?</i>"),
                "<i>[uks kriuksub]</i> <i>Kes seal on?</i>",
                "<i>[uks kriuksub]</i>\n<i>Kes seal on?</i>",
            ),
            (
                ("{\\pos(10,20)}[door creaks]", "Who's there?"),
                "{\\pos(10,20)}[uks kriuksub] Kes seal on?",
                "{\\pos(10,20)}[uks kriuksub]\nKes seal on?",
            ),
        ],
    )
    def test_a_label_with_tags_is_still_a_lone_label(self, source, text, expected):
        assert restore_line_break(text, source) == expected


class TestLength:
    def test_short_text_stays_on_one_line_even_from_a_two_line_source(self):
        text = "Tere, mu vana sõber"
        assert restore_line_break(text, ("Hello there,", "my old friend")) == text

    def test_splits_after_punctuation_when_over_the_limit(self):
        assert restore_line_break(LONG) == "Ma ei tea,\nkas me jõuame täna õhtul koju tagasi"

    def test_never_splits_between_two_capitalised_words(self):
        result = restore_line_break("Ma rääkisin eile õhtul pikalt Mardi Kuusepuu naisega kohvikus")
        assert result == "Ma rääkisin eile õhtul pikalt\nMardi Kuusepuu naisega kohvikus"

    def test_moves_off_a_balanced_break_that_would_split_a_name(self):
        result = restore_line_break("Ma rääkisin eile õhtul Mardi Kuusepuu naisega kohvikus pikalt")
        assert result == "Ma rääkisin eile õhtul Mardi Kuusepuu\nnaisega kohvikus pikalt"

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

    def test_never_breaks_inside_a_brace_tag(self):
        result = restore_line_break(
            "Ma ei tea, kas me homme{\\pos(10, 20)} jõuame koju tagasi või mitte"
        )
        assert result == "Ma ei tea, kas me homme{\\pos(10, 20)}\njõuame koju tagasi või mitte"


def test_leaves_already_multiline_text_unchanged():
    assert restore_line_break("line one\nline two") == "line one\nline two"


def test_single_word_with_no_spaces_unchanged():
    assert restore_line_break("Word") == "Word"
