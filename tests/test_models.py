from __future__ import annotations

from mkv_subtitle_translator.models import DEFAULT_MODEL, SUBTITLE_MODELS, Subtitle, SubtitleType


class TestSubtitleModels:
    def test_default_model_key_exists(self):
        assert DEFAULT_MODEL in SUBTITLE_MODELS

    def test_every_model_has_required_fields(self):
        required = {
            "id",
            "name",
            "cost_per_1m_input",
            "cost_per_1m_output",
            "strengths",
            "tier",
            "recommended_for",
        }
        for key, config in SUBTITLE_MODELS.items():
            missing = required - config.keys()
            assert not missing, f"{key} missing fields: {missing}"

    def test_batch_capable_models_declare_context_limits(self):
        for key, config in SUBTITLE_MODELS.items():
            if config.get("supports_batch"):
                assert "max_context" in config, key
                assert "max_output" in config, key


class TestSubtitleDataclass:
    def test_default_field_values(self):
        sub = Subtitle(index="1", timestamp="00:00:01,000 --> 00:00:02,000", text="Hi")
        assert sub.subtitle_type is None
        assert sub.translated_text is None
        assert sub.line_count == 1

    def test_subtitle_type_values(self):
        assert SubtitleType.DIALOGUE.value == "dialogue"
        assert SubtitleType.NARRATIVE.value == "narrative"
        assert SubtitleType.SOUND_EFFECT.value == "sound_effect"
        assert SubtitleType.UNKNOWN.value == "unknown"
