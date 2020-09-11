from datetime import date, datetime

import pytest

from tasks.time_scope import TimeScope, enclosing_scopes


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


def test_enclosing_scopes():
    ref = TimeScope("2023-ww04.3")
    enclosing = list(enclosing_scopes(ref))

    assert TimeScope("2023—Q1") in enclosing
    assert TimeScope("2023-ww04") in enclosing
