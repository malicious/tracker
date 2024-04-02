from datetime import date, datetime

import pytest

from util import TimeScope, TimeScopeBuilder


def test_create_dt():
    dt0 = datetime(year=2005, month=1, day=31)
    s = TimeScopeBuilder.day_scope_from_dt(dt0)
    assert s is not None
    assert s == "2005-ww05.1"
    s.validate()


def test_prev_day():
    day_ref = TimeScope("2002-ww04.4")
    assert TimeScopeBuilder.prev_scope(day_ref) == "2002-ww04.3"
    assert day_ref.prev == "2002-ww04.3"


def test_prev_next_day():
    day_ref = TimeScope("2002-ww04.4")
    assert TimeScopeBuilder.prev_scope(day_ref) == "2002-ww04.3"
    assert TimeScopeBuilder.next_scope(day_ref) == "2002-ww04.5"
    assert day_ref.prev == "2002-ww04.3"
    assert day_ref.next == "2002-ww04.5"


def test_prev_week():
    week_ref = TimeScope("1988-ww08")
    assert TimeScopeBuilder.prev_scope(week_ref) == "1988-ww07"


def test_prev_next_week():
    wref = TimeScope("2020-ww01")
    assert TimeScopeBuilder.prev_scope(wref) == "2019-ww52"
    assert TimeScopeBuilder.next_scope(wref) == "2020-ww02"
    assert wref.prev == "2019-ww52"
    assert wref.next == "2020-ww02"


def test_prev_next_quarter():
    ref = TimeScope("2020—Q4")
    assert TimeScopeBuilder.prev_scope(ref) == "2020—Q3"
    assert TimeScopeBuilder.next_scope(ref) == "2021—Q1"


def test_parenting():
    day = TimeScope("2024-ww14.2")
    assert day.is_day

    week = TimeScopeBuilder.get_parent_scope(day)
    assert week is not None
    assert week.is_week
    assert week == "2024-ww14"

    quarter = TimeScopeBuilder.get_parent_scope(week)
    assert quarter is not None
    assert quarter.is_quarter
    assert quarter == "2024—Q2"


def test_childing_simple():
    quarter = TimeScope("2024—Q2")

    weeks = TimeScopeBuilder.get_child_scopes(quarter)
    assert "2024-ww14" in weeks
    assert "2024-ww14" == weeks[0]

    days = TimeScopeBuilder.get_child_scopes(weeks[0])
    assert len(days) == 7
    assert "2024-ww14.1" in days
    assert "2024-ww14.1" == days[0]


def test_childing_specific():
    # 2016-01-01 == 2015-ww53.5, so Thursday is still in the prior quarter.
    boundary_week = TimeScope("2015-ww53")
    assert TimeScopeBuilder.get_parent_scope(boundary_week) == "2015—Q4"

    # 2023-10-01 == 2023-ww39.6, so it should belong to the "Q3" list.
    week2 = TimeScope("2023-ww39")
    assert TimeScopeBuilder.get_parent_scope(week2) == "2023—Q3"

    # 2021-04-01 == 2021-ww13.4, should be its own new week in 2021—Q2
    week3 = TimeScope("2021-ww13")
    assert TimeScopeBuilder.get_parent_scope(week3) == "2021—Q2"


def test_childing_exhaustive():
    test_week = TimeScope("2015-ww50")
    while test_week.start < datetime(year=2026, month=1, day=1):
        parent = TimeScopeBuilder.get_parent_scope(test_week)
        children = TimeScopeBuilder.get_child_scopes(parent)

        print(f"[DEBUG] {test_week} => {parent}")
        assert test_week in children
        test_week = test_week.next
