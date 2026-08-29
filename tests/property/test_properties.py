from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from hypothesis import given, strategies as st

from backend import admin, statistics


OUTCOMES = st.lists(st.booleans(), min_size=0, max_size=260)


def rows_from_outcomes(outcomes: list[bool]):
    start = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    return [
        {
            "outcome": "correct" if correct else "incorrect",
            "created_at": (start + timedelta(minutes=index)).isoformat(),
        }
        for index, correct in enumerate(outcomes)
    ]


@given(OUTCOMES, st.integers(min_value=1, max_value=50))
def test_moving_accuracy_respects_range_and_size(outcomes, window):
    series = statistics.moving_accuracy(rows_from_outcomes(outcomes), window=window)

    raw_points = 0 if len(outcomes) < window else len(outcomes) - window + 1
    if raw_points == 0:
        assert series == []
    elif raw_points <= 120:
        assert len(series) == raw_points
    else:
        assert 1 <= len(series) <= 120

    assert all(0.0 <= point["value"] <= 100.0 for point in series)


@given(st.integers(min_value=1, max_value=260), st.integers(min_value=1, max_value=50))
def test_moving_accuracy_is_100_for_only_correct_answers(size, window):
    series = statistics.moving_accuracy(rows_from_outcomes([True] * size), window=window)

    if size < window:
        assert series == []
    else:
        assert series and all(point["value"] == 100.0 for point in series)


@given(st.text())
def test_generated_username_is_always_valid(name):
    username = admin.username_base_from_name(name)

    assert 3 <= len(username) <= 50
    assert re.fullmatch(r"[A-Za-z0-9._-]+", username)


@given(
    st.text(
        alphabet=st.characters(
            blacklist_characters="/\\",
            blacklist_categories=("Cs",),
        ),
        min_size=1,
        max_size=260,
    )
)
def test_clean_attachment_name_never_returns_paths_or_controls(filename):
    try:
        cleaned = admin.clean_attachment_name(f"../../{filename}")
    except ValueError:
        return

    assert cleaned
    assert len(cleaned) <= 180
    assert "/" not in cleaned and "\\" not in cleaned
    assert all(ord(char) >= 32 and ord(char) != 127 for char in cleaned)
