"""Tests unitaires des fonctions pures du collecteur."""

from datetime import UTC, datetime, timedelta

from collector.collect import (
    HOME,
    _project_label,
    fmt_duration,
    minus_one_month,
    observed_pace,
    parse_iso_utc,
    ratio_state,
    today_budget_state,
    weighted_units,
    window_start,
)


def test_parse_iso_utc_handles_z_and_naive():
    dt = parse_iso_utc("2026-01-15T12:00:00Z")
    assert dt.tzinfo is not None
    assert dt == datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
    naive = parse_iso_utc("2026-01-15T12:00:00")
    assert naive.tzinfo == UTC


def test_minus_one_month_clamps_day():
    dt = datetime(2026, 3, 31, tzinfo=UTC)
    out = minus_one_month(dt)
    assert out.month == 2
    assert out.day == 28  # 2026 not leap
    jan = minus_one_month(datetime(2026, 1, 15, tzinfo=UTC))
    assert jan.month == 12 and jan.year == 2025


def test_window_start():
    reset = datetime(2026, 2, 10, 12, 0, tzinfo=UTC)
    assert window_start("rolling", reset) == reset - timedelta(hours=5)
    assert window_start("weekly", reset) == reset - timedelta(days=7)
    assert window_start("monthly", reset).month == 1


def test_ratio_state():
    assert ratio_state(None, 50) == "ok"
    assert ratio_state(None, 90) == "warn"
    assert ratio_state(0.5, 50) == "ok"
    assert ratio_state(0.97, 50) == "warn"
    assert ratio_state(1.2, 50) == "over"
    assert ratio_state(0.5, 100) == "exhausted"


def test_today_budget_state():
    assert today_budget_state(None) == "ok"
    assert today_budget_state(0.9) == "ok"
    assert today_budget_state(1.1) == "warn"
    assert today_budget_state(1.3) == "over"


def test_observed_pace_requires_span_and_delta():
    assert observed_pace([]) is None
    assert observed_pace([(0, 10.0), (100, 11.0)]) is None  # span too short
    rows = [(0, 10.0), (86400 * 2, 30.0)]
    pace = observed_pace(rows)
    assert pace is not None and pace > 0


def test_weighted_units_zero_or_negative_span():
    now = datetime(2026, 2, 1, tzinfo=UTC)
    assert weighted_units(now, now, [1.0] * 7) == 0.0
    assert weighted_units(now, now - timedelta(days=1), [1.0] * 7) == 0.0


def test_weighted_units_full_week_is_sum_of_factors():
    start = datetime(2026, 2, 2, tzinfo=UTC)  # monday
    end = start + timedelta(days=7)
    factors = [1.0] * 7
    assert abs(weighted_units(start, end, factors) - 7.0) < 1e-9


def test_project_label_t3_worktree():
    assert _project_label("/home/x/.t3/worktrees/foo/src") == "foo"
    assert _project_label("") == "?"
    assert _project_label(str(HOME)) == "home"
    assert _project_label("/a/b/myproj") == "myproj"


def test_fmt_duration():
    assert fmt_duration(0) == "maintenant"
    assert fmt_duration(3600) == "1 h 00"
    assert fmt_duration(86400 * 2 + 3600) == "2 j 1 h"
