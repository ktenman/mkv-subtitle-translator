from __future__ import annotations

from mkv_subtitle_translator.analyzer import SubtitleAnalyzer
from mkv_subtitle_translator.models import SubtitleType


class TestDetectSubtitleType:
    def test_fully_bracketed_text_is_sound_effect(self):
        assert SubtitleAnalyzer.detect_subtitle_type("[door slams]") == SubtitleType.SOUND_EFFECT

    def test_dash_prefix_is_dialogue(self):
        assert SubtitleAnalyzer.detect_subtitle_type("- Hello there.") == SubtitleType.DIALOGUE

    def test_lowercase_keyword_is_dialogue(self):
        result = SubtitleAnalyzer.detect_subtitle_type("Hello there, friend.")
        assert result == SubtitleType.DIALOGUE

    def test_partial_bracket_long_text_is_narrative(self):
        text = "They kiss passionately [music swells in the background]"
        assert SubtitleAnalyzer.detect_subtitle_type(text) == SubtitleType.NARRATIVE

    def test_falls_back_to_unknown(self):
        assert SubtitleAnalyzer.detect_subtitle_type("Xyzzy plugh.") == SubtitleType.UNKNOWN


class TestIsSdhSubtitle:
    def test_bracketed_descriptions_detected_as_sdh(self, tmp_path):
        srt = tmp_path / "sdh.srt"
        blocks = [
            f"{i}\n00:00:0{i},000 --> 00:00:0{i + 1},000\n[sound effect {i}]" for i in range(1, 6)
        ]
        srt.write_text("\n\n".join(blocks), encoding="utf-8")
        assert SubtitleAnalyzer.is_sdh_subtitle(str(srt)) is True

    def test_plain_dialogue_not_detected_as_sdh(self, tmp_path):
        srt = tmp_path / "plain.srt"
        blocks = [
            f"{i}\n00:00:0{i},000 --> 00:00:0{i + 1},000\nJust talking normally"
            for i in range(1, 6)
        ]
        srt.write_text("\n\n".join(blocks), encoding="utf-8")
        assert SubtitleAnalyzer.is_sdh_subtitle(str(srt)) is False
