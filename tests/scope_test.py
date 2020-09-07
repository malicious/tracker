from datetime import date, datetime

import pytest

from tracker.scope import TimeScope


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


def test_print_time_scope(test_client):
    r = test_client.get('/time_scope/2020-ww35')
    j = r.get_json()
    assert j['start'] == "2020-08-24 00:00:00"
