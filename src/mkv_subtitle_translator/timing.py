"""Keep each subtitle up long enough to read, without touching the next one."""

from __future__ import annotations

import re
from bisect import bisect_left

from mkv_subtitle_translator.linebreak import _visible
from mkv_subtitle_translator.models import Subtitle

GAP = 0.084  # two frames before the next line
MAX_SHOWN = 7.0
MAX_ADDED = 2.0  # so a line does not hang over the next scene
MIN_SHOWN = 1.0
READ_CPS = 15  # gentler than the 17 cps limit: time taken from a pause costs nothing
LIMIT_CPS = 17

_TIME = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)")


def parse_timestamp(ts: str) -> tuple[float, float] | None:
    times = _TIME.findall(ts)
    if len(times) != 2 or "-->" not in ts:
        return None
    start, end = (int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000 for h, m, s, ms in times)
    return start, end


def _clock(seconds: float) -> str:
    ms = round(seconds * 1000)
    return f"{ms // 3_600_000:02}:{ms // 60_000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


def visible_chars(text: str) -> int:
    return len(_visible(text))


def latest_end(start: float, end: float, next_start: float | None) -> float:
    """The latest a line may stay up. Never earlier than its own end."""
    limit = min(start + MAX_SHOWN, end + MAX_ADDED)
    if next_start is not None:
        limit = min(limit, next_start - GAP)
    return max(end, limit)


def readable_end(start: float, end: float, next_start: float | None, chars: int) -> float:
    needed = start + max(chars / READ_CPS, MIN_SHOWN)
    return max(end, min(needed, latest_end(start, end, next_start)))


def _spans(timestamps: list[str]) -> list[tuple[float, float, float | None] | None]:
    """(start, end, next line's start) for each timestamp, or None when it does not parse."""
    parsed = [parse_timestamp(ts) for ts in timestamps]
    # The next start in time, not in file order. A shared start counts as next, so it blocks.
    starts = sorted(p[0] for p in parsed if p)
    spans = []
    for times in parsed:
        if times is None:
            spans.append(None)
            continue
        j = bisect_left(starts, times[0]) + 1
        spans.append((*times, starts[j] if j < len(starts) else None))
    return spans


def retimed(timestamps: list[str], texts: list[str]) -> list[str]:
    """Timestamps with later end times where a line needs them. Unreadable ones stay as given."""
    out = []
    for ts, span, text in zip(timestamps, _spans(timestamps), texts, strict=True):
        if span is None:
            out.append(ts)
            continue
        start, end, next_start = span
        new_end = readable_end(start, end, next_start, visible_chars(text))
        out.append(f"{_clock(start)} --> {_clock(new_end)}")
    return out


def char_limits(subtitles: list[Subtitle]) -> dict[str, int]:
    """A limit for each line whose English is longer than its longest possible time allows.
    The Estonian runs about as long as the English, so these are the lines to shorten."""
    limits = {}
    for sub, span in zip(subtitles, _spans([s.timestamp for s in subtitles]), strict=True):
        if span is None:
            continue
        start, end, next_start = span
        limit = int((latest_end(start, end, next_start) - start) * LIMIT_CPS)
        if 0 < limit < visible_chars(sub.text):  # a cue with no time gets no limit
            limits[sub.index] = limit
    return limits


def over_speed(timestamps: list[str], texts: list[str]) -> int:
    """How many lines ask for more than LIMIT_CPS characters per second."""
    count = 0
    for ts, text in zip(timestamps, texts, strict=True):
        times = parse_timestamp(ts)
        if (
            times
            and times[1] > times[0]
            and visible_chars(text) / (times[1] - times[0]) > LIMIT_CPS
        ):
            count += 1
    return count
