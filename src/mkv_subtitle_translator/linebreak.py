from __future__ import annotations

import re

# ============================================================================
# Line-break restoration
#
# read_srt() joins multi-line subtitle blocks into a single string (the
# translation protocol sends/receives one line per subtitle). That means a
# 2-line English subtitle always comes back as 1 translated line. Restore the
# original 2-line shape at write time using the same split heuristic: break
# on " - " for two-speaker exchanges, otherwise word-wrap near the midpoint.
# ============================================================================

_WRAP_CONJUNCTIONS = {
    "ja",
    "et",
    "aga",
    "kuid",
    "sest",
    "või",
    "nii",
    "siis",
    "ning",
    "kui",
    "mis",
    "kes",
    "ilma",
}


def _strip_wrap_tags(line: str) -> tuple[str, str, str]:
    """Pull off a leading {\\an8} / <i> and trailing </i> so they don't get
    caught in the middle of a line split."""
    prefix = ""
    suffix = ""
    s = line
    m = re.match(r"^(\{\\an8\})", s)
    if m:
        prefix += m.group(1)
        s = s[m.end() :]
    m2 = re.match(r"^(<i>)", s)
    if m2:
        prefix += m2.group(1)
        s = s[m2.end() :]
        m3 = re.search(r"(</i>)\s*$", s)
        if m3:
            suffix = m3.group(1)
            s = s[: m3.start()]
    return prefix, s, suffix


def _split_dash(s: str) -> tuple[str, str] | None:
    """Split a two-speaker line like '- Hi. - Hello.' into two dash lines."""
    idx = s.find(" - ", 2)
    if idx == -1:
        return None
    line1 = s[:idx].rstrip()
    line2 = "- " + s[idx + 3 :].lstrip()
    return line1, line2


def _split_natural(s: str) -> tuple[str, str] | None:
    """Word-wrap split near the midpoint, preferring a break after a comma
    or before a common conjunction."""
    n = len(s)
    mid = n / 2
    best = None
    best_score = None
    for m in re.finditer(r" ", s):
        pos = m.start()
        if pos < n * 0.25 or pos > n * 0.75:
            continue
        score = abs(pos - mid)
        if pos > 0 and s[pos - 1] in ",:":
            score -= 8
        nxt = s[pos + 1 :].split(" ", 1)[0].strip(".,!?…").lower()
        if nxt in _WRAP_CONJUNCTIONS:
            score -= 4
        if best_score is None or score < best_score:
            best_score = score
            best = pos
    if best is None:
        spaces = [m.start() for m in re.finditer(r" ", s)]
        if not spaces:
            return None
        best = min(spaces, key=lambda p: abs(p - mid))
    line1 = s[:best].rstrip()
    line2 = s[best + 1 :].lstrip()
    return line1, line2


def restore_line_break(text: str) -> str:
    """If text has no embedded newline, split it into two lines so a 2-line
    source subtitle doesn't collapse into one translated line."""
    if "\n" in text:
        return text
    prefix, core, suffix = _strip_wrap_tags(text)
    result = _split_dash(core) if core.startswith("- ") else None
    if result is None:
        result = _split_natural(core)
    if result is None:
        return text
    line1, line2 = result
    return f"{prefix}{line1}\n{line2}{suffix}"


def _demo() -> None:
    assert restore_line_break("single line") != "single line" or " " not in "single line"
    assert restore_line_break("Hello there") == "Hello\nthere" or "\n" in restore_line_break(
        "Hello there"
    )
    two_speaker = restore_line_break("- Are you coming? - Not tonight.")
    assert two_speaker == "- Are you coming?\n- Not tonight."
    tagged = restore_line_break("{\\an8}Hello there, my old friend")
    assert tagged.startswith("{\\an8}") and "\n" in tagged
    already_multiline = "line one\nline two"
    assert restore_line_break(already_multiline) == already_multiline
    assert restore_line_break("Word") == "Word"
    print("linebreak self-check OK")


if __name__ == "__main__":
    _demo()
