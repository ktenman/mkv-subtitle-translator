from __future__ import annotations

import pytest

from mkv_subtitle_translator.models import Subtitle
from mkv_subtitle_translator.timing import (
    char_limits,
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


def test_out_of_order_lines_never_overlap():
    stamps = [
        "00:00:01,000 --> 00:00:02,000",
        "00:00:10,000 --> 00:00:11,000",
        "00:00:03,000 --> 00:00:04,000",
    ]
    assert retimed(stamps, ["x" * 45, "Jah.", "Jah."])[0] == "00:00:01,000 --> 00:00:02,916"


def test_lines_sharing_a_start_are_left_alone():
    stamps = ["00:00:01,000 --> 00:00:02,000"] * 2
    assert retimed(stamps, ["x" * 100] * 2) == stamps


def _sub(i, ts, text):
    return Subtitle(index=str(i), timestamp=ts, text=text)


def test_no_limit_when_the_line_has_time():
    assert char_limits([_sub(1, "00:00:01,000 --> 00:00:02,000", "x" * 40)]) == {}


def test_limit_when_the_next_line_leaves_no_time():
    subs = [
        _sub(1, "00:00:01,000 --> 00:00:01,800", "x" * 40),
        _sub(2, "00:00:01,900 --> 00:00:03,000", "Yes."),
    ]
    assert char_limits(subs) == {"1": 13}  # 0.816 s x 17 cps


def test_no_limit_for_a_cue_with_no_time():
    backwards = [_sub(1, "00:00:05,000 --> 00:00:02,000", "x" * 40)]
    flash = [
        _sub(1, "00:00:05,000 --> 00:00:05,040", "x" * 40),
        _sub(2, "00:00:05,100 --> 00:00:06,000", "Jah."),
    ]
    assert char_limits(backwards) == char_limits(flash) == {}
