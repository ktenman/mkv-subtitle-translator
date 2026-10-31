from __future__ import annotations

import concurrent.futures
import functools
import os
import re
import threading
import time
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path

from tqdm import tqdm

from mkv_subtitle_translator.analyzer import SubtitleAnalyzer
from mkv_subtitle_translator.backends import (
    API_CHUNK_SIZE,
    CLI_WORKERS,
    DEFAULT_BATCH_SIZE,
    DEFAULT_EFFORT,
    FallbackClient,
    QuotaExhausted,
    build_chain,
    uses_cli,
)
from mkv_subtitle_translator.linebreak import restore_line_break
from mkv_subtitle_translator.models import (
    DEFAULT_MODEL,
    Subtitle,
    SubtitleType,
    TranslationStats,
)
from mkv_subtitle_translator.progress import BatchProgress
from mkv_subtitle_translator.prompts import (
    BATCH_SYSTEM_PROMPT,
    CHECK_SYSTEM_PROMPT,
    TERM_SHEET_SYSTEM_PROMPT,
    batch_prompt,
    check_prompt,
    term_sheet_prompt,
)

# Openers mapped to the closers that count as a matching pair.
_QUOTE_PAIRS = {'"': '"', "'": "'", "„": "“”", "“": "”", "«": "»"}
_CURLY_QUOTES = re.compile("[„“”]")

TERM_SHEET_EFFORT = "high"
TERM_SHEET_MAX_TOKENS = 8000


def terms_path(output_path: str) -> str:
    return output_path.removesuffix(".et.srt") + ".et.terms.md"


def read_reference(path: str) -> str:
    """Earlier subtitles as plain text. Older Estonian files are often Windows-1252."""
    raw = Path(path).read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")
    lines = (line.strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line and not line.isdigit() and "-->" not in line)


def strip_wrapping_quotes(text: str) -> str:
    """Drop quotes that wrap the whole line, keeping quotes inside it."""
    text = text.strip()
    if len(text) > 1 and text[-1] in _QUOTE_PAIRS.get(text[0], ""):
        return text[1:-1].strip()
    return text


def _parse_numbered(text: str) -> dict[str, str]:
    """Read the [number] lines of a model reply."""
    parsed = {}
    for line in text.split("\n"):
        match = re.match(r"\[(\d+)\]\s*(.*)", line.strip())
        if match:
            parsed[match.group(1)] = strip_wrapping_quotes(match.group(2))
    return parsed


class OpenRouterTranslator:
    """Subtitle translator using the Codex/Claude CLIs or the OpenRouter API"""

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, effort: str = DEFAULT_EFFORT):
        self.model = model
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
                    source_lines=tuple(line.strip() for line in lines[2:]),
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

            except QuotaExhausted:
                # Same rule as the batch path: never fall back to the English text.
                raise
            except Exception as e:
                print(f"\nTranslation error for #{subtitle.index}: {e}")
                subtitle.translated_text = subtitle.text
                self.stats.failed += 1

        return chunk

    def _batch_translate(
        self,
        subtitles: list[Subtitle],
        batch_size: int = 300,
        *,
        source_name: str = "",
        term_sheet: str = "",
    ) -> list[Subtitle]:
        """Translate subtitles in large batches using models with big context windows.
        Sends many subtitles per API call for massive speed improvement."""
        model_info = self.client.model_config
        max_output = model_info.get("max_output", 65_536)

        print(f"\n{'=' * 60}")
        print(f"Model: {model_info['name']} ({model_info['tier']}) - BATCH MODE")
        print(f"Translating {len(subtitles)} subtitles in batches of {batch_size}")
        print(f"{'=' * 60}", flush=True)

        self._translate_batches(subtitles, batch_size, source_name, term_sheet, max_output)
        return subtitles

    def _run_batches(self, batches: list[list[Subtitle]], call: Callable, finish: Callable) -> None:
        """Run call(number, batch) on workers, 5 at a time on a CLI backend, and
        finish(number, batch, future) here. Only this thread touches self.stats.
        Any exception, Ctrl+C included, cancels what has not started."""
        workers = CLI_WORKERS if uses_cli(self.model) else 1
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(call, number, batch): (number, batch)
                for number, batch in enumerate(batches, 1)
            }
            try:
                for future in concurrent.futures.as_completed(futures):
                    finish(*futures[future], future)
            except BaseException as error:
                # Ctrl+C reaches only this thread, and cancel() can't stop a worker
                # queued for the paid API. Only Ctrl+C, because it ends the process.
                if isinstance(error, KeyboardInterrupt) and isinstance(self.client, FallbackClient):
                    self.client.stopping.set()
                for future in futures:
                    future.cancel()
                raise

    def _translate_batches(
        self,
        subtitles: list[Subtitle],
        batch_size: int,
        source_name: str,
        term_sheet: str,
        max_output: int,
    ) -> None:
        batches = [subtitles[i : i + batch_size] for i in range(0, len(subtitles), batch_size)]

        def call(number: int, batch: list[Subtitle]) -> tuple[str, int, int]:
            progress.start_batch(
                number,
                (batch[0].index, batch[-1].index),
                len(batch),
                self.client.model_config["name"],
            )
            start = (number - 1) * batch_size
            end = start + len(batch)
            user_prompt = batch_prompt(
                source_name,
                term_sheet,
                subtitles[max(0, start - self.context_window_size) : start],
                batch,
                subtitles[end : end + self.context_window_size],
            )

            # 16K tokens is enough for 200 subs (~80 tokens each with overhead)
            est_output_tokens = min(len(batch) * 80, max_output)

            return self.client.translate(
                BATCH_SYSTEM_PROMPT,
                user_prompt,
                max_tokens=est_output_tokens,
                progress=functools.partial(progress.report, number),
            )

        def finish(number: int, batch: list[Subtitle], future: concurrent.futures.Future) -> None:
            completed_before = self.stats.completed
            failed_before = self.stats.failed
            try:
                translated_text, input_tokens, output_tokens = future.result()
                translations = _parse_numbered(translated_text)

                # Apply translations
                for sub in batch:
                    if translations.get(sub.index):
                        sub.translated_text = translations[sub.index]
                        self.stats.completed += 1
                    else:
                        # Fallback: keep original
                        sub.translated_text = sub.text
                        self.stats.failed += 1

                self.stats.input_tokens += input_tokens
                self.stats.output_tokens += output_tokens

            except QuotaExhausted:
                # Every backend is dry - keep going and we'd write English as Estonian.
                raise
            except Exception as e:
                progress.report(number, f"Error: {e}")
                for sub in batch:
                    if not sub.translated_text:
                        sub.translated_text = sub.text
                        self.stats.failed += 1
            progress.finish_batch(
                number,
                self.stats.completed - completed_before,
                self.stats.failed - failed_before,
            )

        with BatchProgress(total=len(subtitles), batches=len(batches)) as progress:
            self._run_batches(batches, call, finish)

    def _chunk_size(self, chunk_size: int | None) -> int:
        if chunk_size is None:
            return DEFAULT_BATCH_SIZE if uses_cli(self.model) else API_CHUNK_SIZE
        return chunk_size

    def _term_sheet(
        self,
        subtitles: list[Subtitle],
        source_name: str,
        output_path: str,
        references: Sequence[str],
    ) -> str:
        """Read the saved sheet, or ask the model for one. Failure is not fatal: the
        batches still translate, only without shared terms."""
        path = Path(terms_path(output_path))
        saved = path.read_text(encoding="utf-8").strip() if path.exists() else ""
        if saved:
            print(f"Reusing term sheet: {path}")
            if references:
                print("--reference files were not read because the term sheet already exists")
            return saved

        reference_texts = [read_reference(reference) for reference in references]
        with BatchProgress(
            total=1, batches=1, stage="Term sheet", label="Term sheet", done="written"
        ) as progress:
            progress.start_batch(
                1,
                (subtitles[0].index, subtitles[-1].index),
                len(subtitles),
                self.client.model_config["name"],
            )
            try:
                sheet, input_tokens, output_tokens = self.client.translate(
                    TERM_SHEET_SYSTEM_PROMPT,
                    term_sheet_prompt(source_name, subtitles, reference_texts),
                    max_tokens=TERM_SHEET_MAX_TOKENS,
                    effort=TERM_SHEET_EFFORT,
                    progress=functools.partial(progress.report, 1),
                )
                if not sheet.strip():
                    raise ValueError("the reply was empty")
            except QuotaExhausted:
                raise
            except Exception as e:
                progress.finish_batch(1, 0, 1)
                print(f"Term sheet failed, continuing without one: {e}")
                return ""
            self.stats.input_tokens += input_tokens
            self.stats.output_tokens += output_tokens
            progress.finish_batch(1, 1, 0)

        path.write_text(f"{sheet}\n", encoding="utf-8")
        print(f"Term sheet saved: {path}")
        return sheet

    def _check_errors(
        self, subtitles: list[Subtitle], source_name: str, term_sheet: str, batch_size: int
    ) -> int:
        """Correct real errors and return how many cues changed. The file is already
        written, so a failed check costs only the corrections it would have made."""
        max_output = self.client.model_config.get("max_output", 65_536)
        batches = [subtitles[i : i + batch_size] for i in range(0, len(subtitles), batch_size)]
        originals: dict[str, str] = {}
        checked = 0

        def call(number: int, batch: list[Subtitle]) -> tuple[str, int, int]:
            progress.start_batch(
                number,
                (batch[0].index, batch[-1].index),
                len(batch),
                self.client.model_config["name"],
            )
            return self.client.translate(
                CHECK_SYSTEM_PROMPT,
                check_prompt(source_name, term_sheet, subtitles, batch),
                max_tokens=min(len(batch) * 80, max_output),
                progress=functools.partial(progress.report, number),
            )

        def finish(number: int, batch: list[Subtitle], future: concurrent.futures.Future) -> None:
            nonlocal checked
            try:
                reply, input_tokens, output_tokens = future.result()
            except QuotaExhausted:
                raise
            except Exception as e:
                progress.report(number, f"Error: {e}")
                progress.finish_batch(number, 0, len(batch))
                return

            self.stats.input_tokens += input_tokens
            self.stats.output_tokens += output_tokens
            corrections = _parse_numbered(reply)
            for sub in batch:
                old = sub.translated_text or sub.text
                new = corrections.get(sub.index)
                if new and new != old:
                    originals[sub.index] = old
                    sub.translated_text = new
            checked += 1
            progress.finish_batch(number, len(batch), 0)

        with BatchProgress(
            total=len(subtitles),
            batches=len(batches),
            stage="Checking",
            label="Check",
            done="checked",
        ) as progress:
            try:
                self._run_batches(batches, call, finish)
            except QuotaExhausted as e:
                print(f"Error check stopped: {e}")

        print(f"Error check corrected {len(originals)} subtitles:")
        for sub in subtitles:
            if sub.index in originals:
                print(f"  #{sub.index}: {originals[sub.index]} -> {sub.translated_text}")
        if checked < len(batches):
            print(f"{len(batches) - checked} of {len(batches)} batches could not be checked")
        return len(originals)

    def translate_file(
        self,
        subtitles: list[Subtitle],
        output_path: str,
        *,
        source_name: str,
        references: Sequence[str] = (),
        chunk_size: int | None = None,
        max_workers: int = 8,
    ) -> None:
        """Run every stage for one file and write the result."""
        chunk_size = self._chunk_size(chunk_size)
        self.stats = TranslationStats(total_subtitles=len(subtitles))
        self.stats.start_time = datetime.now()

        if references and not self.client.model_config.get("supports_batch"):
            print("--reference needs a batch model and was ignored")

        batch_mode = bool(subtitles) and bool(self.client.model_config.get("supports_batch"))
        term_sheet = ""
        if batch_mode:
            term_sheet = self._term_sheet(subtitles, source_name, output_path, references)

        self.translate_subtitles(
            subtitles, chunk_size, max_workers, source_name=source_name, term_sheet=term_sheet
        )
        self.write_srt(subtitles, output_path)
        if batch_mode and self._check_errors(subtitles, source_name, term_sheet, chunk_size):
            self.write_srt(subtitles, output_path)

        self.stats.end_time = datetime.now()
        self.stats.estimated_cost = self.client.estimate_cost(
            self.stats.input_tokens, self.stats.output_tokens
        )
        self._print_stats()

    def translate_subtitles(
        self,
        subtitles: list[Subtitle],
        chunk_size: int | None = None,
        max_workers: int = 8,
        *,
        source_name: str = "",
        term_sheet: str = "",
    ) -> list[Subtitle]:
        """Translate subtitles - uses batch mode for large-context models"""
        chunk_size = self._chunk_size(chunk_size)

        # Auto-detect batch mode for models that support it
        if self.client.model_config.get("supports_batch"):
            return self._batch_translate(
                subtitles, batch_size=chunk_size, source_name=source_name, term_sheet=term_sheet
            )

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
                except QuotaExhausted:
                    pbar.close()
                    raise
                except Exception as e:
                    print(f"\nChunk error: {e}")

        pbar.close()
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
        # ponytail: a kill mid-write leaves the .tmp behind, and the next write replaces it.
        temp_path = f"{output_path}.tmp"
        with open(temp_path, "w", encoding="utf-8-sig") as file:
            for subtitle in subtitles:
                text = _CURLY_QUOTES.sub('"', subtitle.translated_text or subtitle.text)
                text = restore_line_break(text, subtitle.source_lines)
                file.write(f"{subtitle.index}\n{subtitle.timestamp}\n{text}\n\n")
        os.replace(temp_path, output_path)


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
