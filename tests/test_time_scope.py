from datetime import date, datetime

import pytest

from util import TimeScope


def test_create():
    s = TimeScope("2020-ww35")
    assert s
    s.validate()


def test_create_short():
    s = TimeScope("ww35")
    assert s
    s.validate()


def test_invalid():
    with pytest.raises(ValueError):
        s = TimeScope("invalid scope string")
        s.validate()

    with pytest.raises(ValueError):
        # This is invalid because it contains a typo
        s = TimeScope("2020-w35")
        s.validate()


def _construct_dt(year, month, day):
    return datetime.combine(date(year, month, day), datetime.min.time())


def test_day_type():
    s = TimeScope("2020-ww35.5")
    assert s.start == _construct_dt(2020, 8, 28)
    assert s.end == _construct_dt(2020, 8, 29)
    assert s.is_day
    assert not s.is_week
    assert not s.is_quarter


def test_week_type():
    s = TimeScope("2020-ww35")
    assert s.start == _construct_dt(2020, 8, 24)
    assert s.end == _construct_dt(2020, 8, 31)
    assert not s.is_day
    assert s.is_week
    assert not s.is_quarter


def test_quarter_type():
    s = TimeScope("2018—Q3")
    assert s.start == _construct_dt(2018, 7, 1)
    assert s.end == _construct_dt(2018, 10, 1)
    assert not s.is_day
    assert not s.is_week
    assert s.is_quarter
