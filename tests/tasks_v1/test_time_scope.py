from datetime import date, datetime

import pytest

from tasks_v1.time_scope import TimeScope, TimeScopeUtils


def test_create():
    s = TimeScope("2020-ww35")
    assert s


def test_create_short():
    s = TimeScope("ww35")
    assert s


def test_invalid():
    with pytest.raises(ValueError):
        s = TimeScope("invalid scope string")
        s.type

    with pytest.raises(ValueError):
        s = TimeScope("2020-w35")
        s.type


def _construct_dt(year, month, day):
    return datetime.combine(date(year, month, day), datetime.min.time())


def test_week_type():
    s = TimeScope("2020-ww35")
    assert s.type == TimeScope.Type.week
    assert s.start == _construct_dt(2020, 8, 24)
    assert s.end == _construct_dt(2020, 8, 31)


def test_day_type():
    s = TimeScope("2020-ww35.5")
    assert s.type == TimeScope.Type.day
    assert s.start == _construct_dt(2020, 8, 28)
    assert s.end == _construct_dt(2020, 8, 29)


def test_quarter_type():
    s = TimeScope("2018—Q3")
    assert s.type == TimeScope.Type.quarter
    assert s.start == _construct_dt(2018, 7, 1)
    assert s.end == _construct_dt(2018, 10, 1)


def test_print_time_scope(test_client):
    r = test_client.get('/time_scope/2020-ww35')
    j = r.get_json()
    assert j['start'] == "2020-08-24 00:00:00"


def test_shorten_today():
    ref = "2020-ww48.4"
    s = TimeScope("2020-ww48.4").shorten(ref)
    assert not s


def test_shorten_weeks():
    ref = "2020-ww47.3"
    s = TimeScope("2020-ww48.4").shorten(ref)
    assert s == "ww48.4"


def test_shorten_years():
    ref = "2010-ww48.4"
    s = TimeScope("2020-ww48.4").shorten(ref)
    assert s == "2020-ww48.4"


def test_shorten_years_close():
    ref = "2020-ww52.4"
    s = TimeScope("2021-ww02.1").shorten(ref)
    assert s == "2021-ww02.1"


def test_minimize():
    ref = TimeScope("2020-ww48.4")

    assert ref.minimize("2019-ww48.5") == "2019-ww48.5"
    assert ref.minimize("2020-ww48.5") == "ww48.5"
    assert ref.minimize("2020-ww50.4") == "ww50.4"


def test_enclosing_scopes():
    ref = TimeScope("2023-ww04.3")
    assert TimeScopeUtils.enclosing_scope(ref, recurse=False) == [TimeScope("2023-ww04")]
    assert set(TimeScopeUtils.enclosing_scope(ref, recurse=True)) \
           == {TimeScope("2023-ww04"), TimeScope("2023—Q1")}


def test_prev_next_day():
    dref = TimeScope("2002-ww04.4")
    assert TimeScopeUtils.next_scope(dref) == "2002-ww04.5"


def test_prev_next_week():
    wref = TimeScope("2020-ww01")
    assert TimeScopeUtils.prev_scope(wref) == "2019-ww52"
    assert TimeScopeUtils.next_scope(wref) == "2020-ww02"


def test_prev_next_quarter():
    ref = TimeScope("2020—Q4")
    assert TimeScopeUtils.prev_scope(ref) == "2020—Q3"
    assert TimeScopeUtils.next_scope(ref) == "2021—Q1"
