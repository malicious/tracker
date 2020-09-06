from datetime import date, datetime

from tracker.scope import TimeScope


class TestTimeScope:
    def test_create(self):
        s = TimeScope("2020-ww35")
        assert s

    def test_create_short(self):
        s = TimeScope("ww35")
        assert s

    @staticmethod
    def construct_dt(year, month, day):
        return datetime.combine(date(year, month, day), datetime.min.time())

    def test_week_type(self):
        s = TimeScope("2020-ww35")
        assert s.type == TimeScope.Type.week
        assert s.start == TestTimeScope.construct_dt(2020, 8, 24)
        assert s.end == TestTimeScope.construct_dt(2020, 8, 31)

    def test_day_type(self):
        s = TimeScope("2020-ww35.5")
        assert s.type == TimeScope.Type.day
        assert s.start == TestTimeScope.construct_dt(2020, 8, 28)
        assert s.end == TestTimeScope.construct_dt(2020, 8, 29)
