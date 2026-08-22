from __future__ import annotations

import concurrent.futures
import re
import threading
import time
from datetime import datetime

from tqdm import tqdm

from mkv_subtitle_translator.analyzer import SubtitleAnalyzer
from mkv_subtitle_translator.backends import DEFAULT_EFFORT, QuotaExhausted, build_chain
from mkv_subtitle_translator.linebreak import restore_line_break
from mkv_subtitle_translator.models import (
    DEFAULT_MODEL,
    Subtitle,
    SubtitleType,
    TranslationStats,
)

# Openers mapped to the closers that count as a matching pair.
_QUOTE_PAIRS = {'"': '"', "'": "'", "„": "“”", "“": "”", "«": "»"}


def strip_wrapping_quotes(text: str) -> str:
    """Drop quotes that wrap the whole line, keeping quotes inside it."""
    text = text.strip()
    if len(text) > 1 and text[-1] in _QUOTE_PAIRS.get(text[0], ""):
        return text[1:-1].strip()
    return text


class OpenRouterTranslator:
    """Subtitle translator using the Codex/Claude CLIs or the OpenRouter API"""

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, effort: str = DEFAULT_EFFORT):
        self.client = build_chain(model, effort, api_key)
        self.analyzer = SubtitleAnalyzer()
        self.context_window_size = 5  # Increased for better context
        self.glossary = self._create_translation_glossary()
        self.translation_cache = {}
        self.cache_lock = threading.Lock()
        self.stats = TranslationStats()

    def _create_translation_glossary(self) -> dict:
        """Create a glossary of context-dependent translations"""
        return {
            "honey": {"dialogue": "kallis", "narrative": "mesi"},
            "sweetheart": {"dialogue": "kullake", "narrative": "magus süda"},
            "dear": {"dialogue": "armas", "narrative": "kallis"},
            "baby": {"dialogue": "kallis", "narrative": "beebi"},
            "darling": {"dialogue": "kallis", "narrative": "lemmiksõna"},
            "sweetie": {"dialogue": "kullake", "narrative": "magus"},
            "break a leg": {"all": "edu sulle"},
            "piece of cake": {"all": "lihtne kui lusikatäis"},
            "it's raining cats and dogs": {"all": "sajab nagu oavarrest"},
        }

    def read_srt(self, file_path: str) -> list[Subtitle]:
        """Read SRT file and return list of Subtitle objects"""
        with open(file_path, encoding="utf-8-sig") as file:
            content = file.read()

        blocks = re.split(r"\n\n+", content.strip())
        subtitles = []

        for block in blocks:
            lines = block.split("\n")
            if len(lines) >= 3:
                index = lines[0].strip()
                timestamp = lines[1].strip()
                text = " ".join(line.strip() for line in lines[2:])

                subtitle_type = self.analyzer.detect_subtitle_type(text)
                subtitle = Subtitle(
                    index=index,
                    timestamp=timestamp,
                    text=text,
                    subtitle_type=subtitle_type,
                    line_count=len(lines[2:]),
                )
                subtitles.append(subtitle)

        return subtitles

    def _create_system_prompt(self, subtitle_type: SubtitleType) -> str:
        """Create a system prompt tailored to the subtitle type"""
        base_prompt = """You are an expert subtitle translator specializing in \
English to Estonian translation.

CRITICAL RULES:
1. Return ONLY the Estonian translation - no explanations, no English, no quotes
2. Keep translations natural and conversational
3. Match the emotional tone and register of the original
4. Preserve any formatting (italics markers, etc.)"""

        if subtitle_type == SubtitleType.DIALOGUE:
            return (
                base_prompt
                + """

DIALOGUE-SPECIFIC RULES:
- Terms of endearment (honey, dear, sweetheart, baby, darling) → Estonian \
endearments (kallis, kullake, armas) NOT literal translations
- Use appropriate formality (sina/teie) based on relationship context
- Translate idioms to Estonian equivalents, not literally
- Keep contractions and casual speech natural"""
            )

        elif subtitle_type == SubtitleType.SOUND_EFFECT:
            return (
                base_prompt
                + """

SOUND EFFECT/SDH RULES:
- Keep descriptions in brackets [näide] or parentheses (näide)
- Translate concisely: [door slams] → [uks paugub]
- Preserve the same punctuation style"""
            )

        else:
            return (
                base_prompt
                + """

Keep subtitle length reasonable while maintaining accuracy.
Preserve any formatting or emphasis from the original."""
            )

    def _build_context_prompt(
        self, current_text: str, current_type: SubtitleType, context_texts: list[str]
    ) -> str:
        """Build a user prompt that includes conversational context"""
        prompt_parts = []

        # Add glossary hints
        glossary_hints = []
        text_lower = current_text.lower()

        for term, translations in self.glossary.items():
            if term in text_lower:
                if "all" in translations:
                    glossary_hints.append(f'"{term}" → "{translations["all"]}"')
                elif current_type == SubtitleType.DIALOGUE and "dialogue" in translations:
                    glossary_hints.append(f'"{term}" (endearment) → "{translations["dialogue"]}"')

        if glossary_hints:
            prompt_parts.append("Translation hints:")
            prompt_parts.extend(glossary_hints)
            prompt_parts.append("")

        # Add context
        if context_texts:
            prompt_parts.append("Recent dialogue context:")
            for i, ctx_text in enumerate(context_texts[-5:], 1):
                prompt_parts.append(f"  {i}. {ctx_text}")
            prompt_parts.append("")

        prompt_parts.append("Translate to Estonian:")
        prompt_parts.append(f'"{current_text}"')

        return "\n".join(prompt_parts)

    def translate_chunk(
        self, chunk: list[Subtitle], all_subtitles: list[Subtitle]
    ) -> list[Subtitle]:
        """Translate a chunk of subtitles with context"""
        for subtitle in chunk:
            try:
                # Check cache
                with self.cache_lock:
                    if subtitle.text in self.translation_cache:
                        subtitle.translated_text = self.translation_cache[subtitle.text]
                        self.stats.cached += 1
                        continue

                # Get context
                subtitle_idx = next(
                    (i for i, s in enumerate(all_subtitles) if s.index == subtitle.index), 0
                )
                context_texts = []
                for i in range(max(0, subtitle_idx - self.context_window_size), subtitle_idx):
                    context_texts.append(all_subtitles[i].text)

                # Create prompts
                system_prompt = self._create_system_prompt(subtitle.subtitle_type)
                user_prompt = self._build_context_prompt(
                    subtitle.text, subtitle.subtitle_type, context_texts
                )

                # Translate
                translated_text, input_tokens, output_tokens = self.client.translate(
                    system_prompt, user_prompt
                )

                # Clean up response (remove quotes if present)
                translated_text = strip_wrapping_quotes(translated_text)
                subtitle.translated_text = translated_text

                # Update stats
                self.stats.input_tokens += input_tokens
                self.stats.output_tokens += output_tokens
                self.stats.completed += 1

                # Cache result
                with self.cache_lock:
                    self.translation_cache[subtitle.text] = translated_text

                # Rate limiting
                time.sleep(0.05)

            except Exception as e:
                print(f"\nTranslation error for #{subtitle.index}: {e}")
                subtitle.translated_text = subtitle.text
                self.stats.failed += 1

        return chunk

    def _batch_translate(self, subtitles: list[Subtitle], batch_size: int = 300) -> list[Subtitle]:
        """Translate subtitles in large batches using models with big context windows.
        Sends many subtitles per API call for massive speed improvement."""
        self.stats = TranslationStats(total_subtitles=len(subtitles))
        self.stats.start_time = datetime.now()

        model_info = self.client.model_config
        max_output = model_info.get("max_output", 65_536)

        print(f"\n{'=' * 60}")
        print(f"Model: {model_info['name']} ({model_info['tier']}) - BATCH MODE")
        print(f"Translating {len(subtitles)} subtitles in batches of {batch_size}")
        print(f"{'=' * 60}")

        batches = [subtitles[i : i + batch_size] for i in range(0, len(subtitles), batch_size)]

        pbar = tqdm(total=len(batches), desc="Batch translating")

        for batch_idx, batch in enumerate(batches):
            try:
                # Build numbered list of subtitles
                lines = []
                for sub in batch:
                    lines.append(f"[{sub.index}] {sub.text}")
                subtitle_block = "\n".join(lines)

                system_prompt = """You are an expert subtitle translator specializing in \
English to Estonian translation.

CRITICAL RULES:
1. Translate ALL subtitles from English to Estonian
2. Return ONLY the translations in the EXACT same format: [number] translated text
3. Keep the [number] prefix exactly as given
4. Do NOT skip any subtitle - translate every single one
5. Do NOT add explanations, notes, or comments
6. Terms of endearment (honey, dear, sweetheart, baby, darling) → Estonian \
endearments (kallis, kullake, armas) NOT literal translations like "mesi"
7. Use natural, conversational Estonian
8. Translate idioms to Estonian equivalents, not literally
9. Keep sound effects in brackets: [door slams] → [uks paugub]
10. Preserve any formatting (italics, dashes for speaker changes)"""

                user_prompt = f"""Translate all {len(batch)} subtitles below to Estonian. \
Return each line as [number] Estonian translation.

{subtitle_block}"""

                # 16K tokens is enough for 200 subs (~80 tokens each with overhead)
                est_output_tokens = min(len(batch) * 80, max_output)

                translated_text, input_tokens, output_tokens = self.client.translate(
                    system_prompt, user_prompt, max_tokens=est_output_tokens
                )

                # Parse response - match [number] translation lines
                translations = {}
                for line in translated_text.split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    match = re.match(r"\[(\d+)\]\s*(.*)", line)
                    if match:
                        idx = match.group(1)
                        trans = strip_wrapping_quotes(match.group(2))
                        translations[idx] = trans

                # Apply translations
                matched = 0
                for sub in batch:
                    if sub.index in translations:
                        sub.translated_text = translations[sub.index]
                        matched += 1
                        self.stats.completed += 1
                    else:
                        # Fallback: keep original
                        sub.translated_text = sub.text
                        self.stats.failed += 1

                self.stats.input_tokens += input_tokens
                self.stats.output_tokens += output_tokens

                if matched < len(batch):
                    print(f"\n  Batch {batch_idx + 1}: {matched}/{len(batch)} matched")

                pbar.update(1)

            except QuotaExhausted:
                # Every backend is dry - keep going and we'd write English as Estonian.
                pbar.close()
                raise
            except Exception as e:
                print(f"\n  Batch {batch_idx + 1} error: {e}")
                for sub in batch:
                    if not sub.translated_text:
                        sub.translated_text = sub.text
                        self.stats.failed += 1
                pbar.update(1)

        pbar.close()
        self.stats.end_time = datetime.now()
        self.stats.estimated_cost = self.client.estimate_cost(
            self.stats.input_tokens, self.stats.output_tokens
        )
        self._print_stats()
        return subtitles

    def translate_subtitles(
        self, subtitles: list[Subtitle], chunk_size: int = 50, max_workers: int = 8
    ) -> list[Subtitle]:
        """Translate subtitles - uses batch mode for large-context models"""
        # Auto-detect batch mode for models that support it
        if self.client.model_config.get("supports_batch"):
            return self._batch_translate(subtitles, batch_size=chunk_size)

        self.stats = TranslationStats(total_subtitles=len(subtitles))
        self.stats.start_time = datetime.now()

        # Split into chunks
        chunks = [subtitles[i : i + chunk_size] for i in range(0, len(subtitles), chunk_size)]

        model_info = self.client.model_config
        print(f"\n{'=' * 60}")
        print(f"Model: {model_info['name']} ({model_info['tier']})")
        print(f"Translating {len(subtitles)} subtitles in {len(chunks)} chunks")
        print(f"Workers: {max_workers}")
        print(f"{'=' * 60}")

        pbar = tqdm(total=len(chunks), desc="Translating")

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for chunk in chunks:
                future = executor.submit(self.translate_chunk, chunk, subtitles)
                futures.append(future)

            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                    pbar.update(1)
                except Exception as e:
                    print(f"\nChunk error: {e}")

        pbar.close()
        self.stats.end_time = datetime.now()

        # Calculate final cost
        self.stats.estimated_cost = self.client.estimate_cost(
            self.stats.input_tokens, self.stats.output_tokens
        )

        self._print_stats()
        return subtitles

    def _print_stats(self):
        """Print translation statistics"""
        duration = self.stats.end_time - self.stats.start_time

        print(f"\n{'=' * 60}")
        print("TRANSLATION COMPLETE")
        print(f"{'=' * 60}")
        print(f"Total: {self.stats.total_subtitles}")
        print(f"Completed: {self.stats.completed}")
        print(f"Cached: {self.stats.cached}")
        print(f"Failed: {self.stats.failed}")
        print(f"Duration: {duration}")
        print(f"Tokens: {self.stats.input_tokens:,} in / {self.stats.output_tokens:,} out")
        print(f"Estimated cost: ${self.stats.estimated_cost:.4f}")
        print(f"{'=' * 60}")

    def write_srt(self, subtitles: list[Subtitle], output_path: str):
        """Write translated subtitles to a new SRT file"""
        with open(output_path, "w", encoding="utf-8-sig") as file:
            for subtitle in subtitles:
                text = subtitle.translated_text or subtitle.text
                if subtitle.line_count == 2:
                    text = restore_line_break(text)
                file.write(f"{subtitle.index}\n{subtitle.timestamp}\n{text}\n\n")


def deduplicate_subtitles(subtitles: list[Subtitle]) -> list[Subtitle]:
    """Remove duplicate subtitles"""
    seen = set()
    deduped = []

    for subtitle in subtitles:
        key = (subtitle.timestamp.strip(), subtitle.text.strip())
        if key not in seen:
            seen.add(key)
            deduped.append(subtitle)

    return deduped
