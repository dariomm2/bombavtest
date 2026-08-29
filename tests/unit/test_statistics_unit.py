from __future__ import annotations

from datetime import date, datetime

from backend import auth, statistics


def test_madrid_day_bounds_handle_dst_days():
    spring_start, spring_end = auth.madrid_day_bounds(date(2026, 3, 29))
    autumn_start, autumn_end = auth.madrid_day_bounds(date(2026, 10, 25))

    spring_hours = (datetime.fromisoformat(spring_end) - datetime.fromisoformat(spring_start)).total_seconds() / 3600
    autumn_hours = (datetime.fromisoformat(autumn_end) - datetime.fromisoformat(autumn_start)).total_seconds() / 3600

    assert spring_hours == 23
    assert autumn_hours == 25


def test_moving_accuracy_uses_sliding_window():
    rows = [
        {"outcome": "correct" if i < 3 else "incorrect", "created_at": f"2026-08-{i + 1:02d}T12:00:00+00:00"}
        for i in range(5)
    ]

    assert statistics.moving_accuracy(rows, window=3) == [
        {"label": "3 ago", "value": 100.0},
        {"label": "4 ago", "value": 66.7},
        {"label": "5 ago", "value": 33.3},
    ]
