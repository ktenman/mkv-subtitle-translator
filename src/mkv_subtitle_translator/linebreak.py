from __future__ import annotations

import re
from collections.abc import Sequence

# ============================================================================
# Line-break restoration
#
# read_srt() joins multi-line subtitle blocks into a single string (the
# translation protocol sends/receives one line per subtitle). Lay the line out
# again at write time from the source cue's lines: two speakers, a lone [label],
# one line if it fits, otherwise the best space. The words never change, and no
# prompt mentions layout, because line rules in a prompt lowered quality.
# ============================================================================

MAX_LINE_LENGTH = 42

# A dash before a space or a letter: -5 and -- are not speaker changes.
_DASH = r"(?:<[^>]*>)*\s*[-–—](?=\s|[^\W\d_])"  # noqa: RUF001
_SPEAKER_DASH = re.compile(r"^(?:\{[^}]*\})?" + _DASH)
_INNER_DASH = re.compile(r"\s" + _DASH)
_LABEL = re.compile(r"\[[^\]]+\]")
_LABEL_START = re.compile(r"(\[[^\]]+\])\s+(.+)")
_TAG = re.compile(r"<[^>]*>|\{[^}]*\}")
_SPACE_OUTSIDE_TAG = re.compile(r" (?![^<>]*>)")
_NO_BREAK_AFTER = set(
    "ja ning ega ehk või et kui aga vaid kuid sest mis kes kus ei on see seda selle oma mu su "  # noqa: SIM905
    "ta ma sa me te nad üks ühe mitte nii kas ka the a an of to".split()
)


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


def _visible(s: str) -> str:
    return _TAG.sub("", s).strip()


def _split_dash(s: str) -> tuple[str, str] | None:
    """Split at the second speaker's dash. Search from 1 to skip the first speaker's."""
    m = _INNER_DASH.search(s, 1)
    if m is None:
        return None
    return s[: m.start()].rstrip(), s[m.start() + 1 :].lstrip()


def _split_label(s: str) -> tuple[str, str] | None:
    m = _LABEL_START.fullmatch(s)
    return (m.group(1), m.group(2)) if m else None


def _split_natural(s: str) -> tuple[str, str] | None:
    """The cheapest break: both lines within the limit and close in length."""
    # ponytail: costs tuned by hand on 13,352 cues, word lists instead of Estonian
    # grammar. A parser is only worth it if a blind read finds bad breaks.
    best = None
    best_cost = None
    for m in _SPACE_OUTSIDE_TAG.finditer(s):
        left, right = s[: m.start()], s[m.end() :]
        a, b = _visible(left), _visible(right)
        if not a or not b:
            continue
        cost = abs(len(a) - len(b))
        if max(len(a), len(b)) > MAX_LINE_LENGTH:
            cost += 1000
        last, first = a.split()[-1], b.split()[0]
        if a[-1] in ",.;:!?…":
            cost -= 25
        elif last[0].isupper() and first[0].isupper():
            cost += 60
        if last.lower() in _NO_BREAK_AFTER:
            cost += 15
        if last[-1].isdigit():
            cost += 30
        if first in ("-", "–", "—", "♪"):  # noqa: RUF001
            cost += 30
        if best_cost is None or cost < best_cost:
            best, best_cost = (left.strip(), right.strip()), cost
    return best


def restore_line_break(text: str, source_lines: Sequence[str] = ()) -> str:
    """Lay out one translated line from the source cue's lines. The words never change."""
    if "\n" in text:
        return text
    prefix, core, suffix = _strip_wrap_tags(text)
    result = None
    if len(source_lines) == 2:
        if _SPEAKER_DASH.match(source_lines[1]):
            result = _split_dash(core)
        elif _LABEL.fullmatch(source_lines[0]):
            result = _split_label(core)
    if result is None:
        if len(_visible(text)) <= MAX_LINE_LENGTH:
            return text
        result = _split_natural(core)
    if result is None:
        return text
    return f"{prefix}{result[0]}\n{result[1]}{suffix}"


def _demo() -> None:
    assert restore_line_break("Hello there") == "Hello there"
    source = ("- Are you?", "- No.")
    two_speaker = restore_line_break("- Are you coming? - Not tonight.", source)
    assert two_speaker == "- Are you coming?\n- Not tonight."
    label = restore_line_break("[door creaks] Who's there?", ("[door creaks]", "Who?"))
    assert label == "[door creaks]\nWho's there?"
    tagged = restore_line_break("{\\an8}Hello there, my old friend, how have you been lately?")
    assert tagged.startswith("{\\an8}") and "\n" in tagged
    already_multiline = "line one\nline two"
    assert restore_line_break(already_multiline) == already_multiline
    assert restore_line_break("Word") == "Word"
    print("linebreak self-check OK")


if __name__ == "__main__":
    _demo()
