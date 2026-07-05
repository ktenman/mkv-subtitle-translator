from __future__ import annotations

import re

from mkv_subtitle_translator.models import SubtitleType


class SubtitleAnalyzer:
    """Analyzes subtitles to determine their type and context"""

    @staticmethod
    def detect_subtitle_type(text: str) -> SubtitleType:
        """Detect if subtitle is dialogue, narrative, or sound effect"""
        if re.search(r"[\[\(].*?[\]\)]", text):
            if re.match(r"^[\[\(][^\]\)]+[\]\)]\s*$", text.strip()):
                return SubtitleType.SOUND_EFFECT
            if len(text.strip()) > 20:
                return SubtitleType.NARRATIVE

        dialogue_patterns = [
            r"^[-–—]",  # noqa: RUF001 (hyphen, en dash, em dash)
            r'^".*"',
            r"^[A-Z][A-Z\s]+:",
        ]

        for pattern in dialogue_patterns:
            if re.search(pattern, text.strip()):
                return SubtitleType.DIALOGUE

        dialogue_keywords = [
            "I ",
            "I'm ",
            "I've ",
            "I'll ",
            "I'd ",
            "you ",
            "you're ",
            "you've ",
            "you'll ",
            "you'd ",
            "we ",
            "we're ",
            "we've ",
            "we'll ",
            "we'd ",
            "my ",
            "your ",
            "our ",
            "me ",
            "us ",
            "yes",
            "no",
            "okay",
            "yeah",
            "please",
            "thanks",
            "sorry",
            "excuse",
            "hello",
            "goodbye",
            "bye",
            "honey",
            "dear",
            "darling",
            "sweetie",
            "baby",
        ]

        text_lower = text.lower()
        if any(keyword in text_lower for keyword in dialogue_keywords):
            return SubtitleType.DIALOGUE

        return SubtitleType.UNKNOWN

    @staticmethod
    def is_sdh_subtitle(file_path: str, sample_size: int = 50) -> bool:
        """Check if a subtitle file appears to be SDH"""
        try:
            with open(file_path, encoding="utf-8-sig") as file:
                content = file.read()

            sdh_patterns = [r"\[.*?\]", r"\(.*?\)", r"♪.*?♪"]
            blocks = re.split(r"\n\n+", content.strip())
            if not blocks:
                return False

            sample_blocks = blocks[:sample_size] if len(blocks) > sample_size else blocks
            sdh_count = 0

            for block in sample_blocks:
                lines = block.split("\n")
                if len(lines) >= 3:
                    text = " ".join(lines[2:])
                    for pattern in sdh_patterns:
                        if re.search(pattern, text):
                            sdh_count += 1
                            break

            sdh_percentage = (sdh_count / len(sample_blocks)) * 100
            is_sdh = sdh_percentage > 10

            if is_sdh:
                print(f"  Detected as SDH subtitle ({sdh_percentage:.1f}% descriptions)")

            return is_sdh

        except Exception as e:
            print(f"  Error checking for SDH: {e}")
            return False
