from __future__ import annotations

from mkv_subtitle_translator.models import Subtitle

BATCH_SYSTEM_PROMPT = """You are an expert subtitle translator specializing in \
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
10. Preserve any formatting (italics, dashes for speaker changes)
11. Use the names, terms and sina or teie from the term sheet.
12. Lines under "Context only" are for understanding. Do not return them."""


def numbered(subtitles: list[Subtitle]) -> str:
    return "\n".join(f"[{sub.index}] {sub.text}" for sub in subtitles)


def batch_prompt(
    source_name: str,
    term_sheet: str,
    before: list[Subtitle],
    batch: list[Subtitle],
    after: list[Subtitle],
) -> str:
    sections = [
        f"Source file: {source_name}" if source_name else "",
        f"Term sheet:\n{term_sheet}" if term_sheet else "",
        f"Context only, earlier subtitles:\n{numbered(before)}" if before else "",
        f"Translate all {len(batch)} subtitles below to Estonian. "
        f"Return each line as [number] Estonian translation.\n\n{numbered(batch)}",
        f"Context only, later subtitles:\n{numbered(after)}" if after else "",
    ]
    return "\n\n".join(section for section in sections if section)
