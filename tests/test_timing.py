from __future__ import annotations

import pytest

from mkv_subtitle_translator.timing import (
    over_speed,
    parse_timestamp,
    readable_end,
    retimed,
    visible_chars,
)


@pytest.mark.parametrize(
    ("start", "end", "next_start", "chars", "expected"),
    [
        (1.0, 2.0, 10.0, 45, 4.0),  # 45 chars need 3 s, capped at the original end + 2 s
        (1.0, 2.0, 2.5, 45, 2.416),  # stops two frames before the next line
        (1.0, 2.0, 10.0, 10, 2.0),  # already readable, never shorter
        (1.0, 1.5, 10.0, 3, 2.0),  # at least 1 s on screen
        (0.0, 6.5, 20.0, 200, 7.0),  # at most 7 s on screen
        (1.0, 3.0, 2.0, 100, 3.0),  # a line overlapping the next is left alone
        (1.0, 2.0, None, 45, 4.0),  # the last line
    ],
)
def test_readable_end(start, end, next_start, chars, expected):
    assert readable_end(start, end, next_start, chars) == pytest.approx(expected)


def test_tags_do_not_count_as_characters():
    assert visible_chars("<i>Tere</i> {\\an8}sina") == 9


def test_keeps_a_timestamp_it_cannot_read():
    assert retimed(["t"], ["x"]) == ["t"]


def test_the_next_line_bounds_the_one_before():
    stamps = ["00:00:01,000 --> 00:00:02,000", "00:00:02,500 --> 00:00:03,000"]
    out = retimed(stamps, ["x" * 45, "Jah."])
    assert out[0] == "00:00:01,000 --> 00:00:02,416"
    assert parse_timestamp(out[1]) == (2.5, 3.5)


def test_counts_lines_over_the_reading_speed():
    assert over_speed(["00:00:01,000 --> 00:00:02,000"], ["x" * 18]) == 1
    assert over_speed(["00:00:01,000 --> 00:00:02,000"], ["x" * 17]) == 0
