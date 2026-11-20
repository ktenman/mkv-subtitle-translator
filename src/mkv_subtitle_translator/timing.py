"""Keep each subtitle up long enough to read, without touching the next one."""

from __future__ import annotations

import re
from bisect import bisect_left

from mkv_subtitle_translator.linebreak import _TAG

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


def format_timestamp(start: float, end: float) -> str:
    return f"{_clock(start)} --> {_clock(end)}"


def visible_chars(text: str) -> int:
    return len(_TAG.sub("", text).strip())


def latest_end(start: float, end: float, next_start: float | None) -> float:
    """The latest a line may stay up. Never earlier than its own end."""
    limit = min(start + MAX_SHOWN, end + MAX_ADDED)
    if next_start is not None:
        limit = min(limit, next_start - GAP)
    return max(end, limit)


def readable_end(start: float, end: float, next_start: float | None, chars: int) -> float:
    needed = start + max(chars / READ_CPS, MIN_SHOWN)
    return max(end, min(needed, latest_end(start, end, next_start)))


def retimed(timestamps: list[str], texts: list[str]) -> list[str]:
    """Timestamps with later end times where a line needs them. Unreadable ones stay as given."""
    parsed = [parse_timestamp(ts) for ts in timestamps]
    # The next start in time, not in file order. A shared start counts as next, so it blocks.
    starts = sorted(p[0] for p in parsed if p)
    out = []
    for ts, times, text in zip(timestamps, parsed, texts, strict=True):
        if times is None:
            out.append(ts)
            continue
        start, end = times
        j = bisect_left(starts, start) + 1
        next_start = starts[j] if j < len(starts) else None
        out.append(
            format_timestamp(start, readable_end(start, end, next_start, visible_chars(text)))
        )
    return out


def over_speed(timestamps: list[str], texts: list[str], cps: float = LIMIT_CPS) -> int:
    """How many lines ask for more than cps characters per second."""
    count = 0
    for ts, text in zip(timestamps, texts, strict=True):
        times = parse_timestamp(ts)
        if times and times[1] > times[0] and visible_chars(text) / (times[1] - times[0]) > cps:
            count += 1
    return count
