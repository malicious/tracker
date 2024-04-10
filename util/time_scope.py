import functools
import re
from datetime import date, datetime, timedelta
from enum import Enum
from typing import List, Self


class TimeScope(str):
    """
    String that encodes a stretch of time

    These are meant to be 1) human-readable and 2) stored in an SQLite database.
    Ignore caching/performance concerns until they're definitely a problem.

    - quarter scopes, which use an emdash ("2021—Q3")
    - week scopes ("2021-ww32"), monday-sunday inclusive
    - day scopes (written as "2021-ww32.1")

    The numbers match ISO 8601, but formatting does not.
    Note that the alphabetic sorting of quarters is problematic, so for the
    most part we treat them as distinct/top-level entities.

    Variable naming convention: flat strings are usually named `scope_id`,
    while objects of type TimeScope are usually named `scope`.
    """

    class Type(Enum):
        day = 1
        week = 7
        quarter = 90

    def __new__(cls, scope_str: str):
        # If we skipped the year prefix on the scope, assume it's this year
        if scope_str[0:2] == "ww":
            scope_str = f"{date.today().year}-{scope_str}"

        return str.__new__(cls, scope_str)

    def validate(self):
        self._build_properties()

        # Check for weird ones like "2018-ww53.1", which should use the ISO year of 2019.
        if self._type == TimeScope.Type.day:
            start_str = self.start.strftime('%G-ww%V.%u')
            if start_str != self:
                raise ValueError(f"Got inconsistent TimeScope: {self} <> {start_str}")

    def _build_properties(self):
        """
        Provides support for a custom time-scope format used in my notes

        - days are canonically specified as: `2020-ww35.5`
        - weeks as: `2020-ww35`
        - quarters as: `2020—Q3` (note that that is an em dash)
        """

        def dt_from_iso(year, week, weekday) -> datetime:
            return datetime.strptime(f'{year} {week} {weekday}', '%G %V %u')

        m = re.fullmatch(r"(\d\d\d\d)-ww([0-5]\d)", self)
        if m:
            self._type = TimeScope.Type.week
            self._dt_start = dt_from_iso(m[1], m[2], 1)
            self._dt_end = self._dt_start + timedelta(days=7)
            return

        m = re.fullmatch(r"(\d\d\d\d)-ww([0-5]\d)\.(\d)", self)
        if m:
            self._type = TimeScope.Type.day
            self._dt_start = dt_from_iso(m[1], m[2], m[3])
            self._dt_end = self._dt_start + timedelta(days=1)
            return

        m = re.fullmatch(r"(\d\d\d\d)—Q([1-4])", self)
        if m:
            self._type = TimeScope.Type.quarter
            year = int(m[1])
            month = int(m[2]) * 3 - 2

            # So, we don't actually use calendar quarters.
            # Every quarter has a whole number of weeks.
            technical_start_day = TimeScopeBuilder.day_scope_from_dt(datetime(year, month, 1))
            technical_start_week = TimeScopeBuilder.get_parent_scope(technical_start_day)

            # If the first of the month is after Thursday, that week belongs to the previous quarter.
            actual_start_week = technical_start_week
            if technical_start_day[-1] in ("5", "6", "7"):
                actual_start_week = TimeScopeBuilder.next_scope(technical_start_week)

            self._dt_start = actual_start_week.start

            # And for the last week: look for one where we own the Thursday.
            if month == 10:
                technical_end_day = TimeScopeBuilder.day_scope_from_dt(datetime(year + 1, 1, 1))
            else:
                technical_end_day = TimeScopeBuilder.day_scope_from_dt(datetime(year, month + 3, 1))
            technical_end_week = TimeScopeBuilder.get_parent_scope(technical_end_day)

            actual_end_week = technical_end_week
            if technical_end_day[-1] in ("5", "6", "7"):
                actual_end_week = TimeScopeBuilder.next_scope(technical_end_week)

            self._dt_end = actual_end_week.start

            return

        raise ValueError(f"Couldn't parse TimeScope: {repr(self)}")

    @property
    def start(self) -> datetime:
        if not hasattr(self, "_dt_start"):
            self._build_properties()

        return self._dt_start

    @property
    def end(self) -> datetime:
        if not hasattr(self, "_dt_end"):
            self._build_properties()

        return self._dt_end

    @property
    def is_day(self) -> bool:
        if not hasattr(self, "_type"):
            self._build_properties()

        return self._type == TimeScope.Type.day

    @property
    def is_week(self) -> bool:
        if not hasattr(self, "_type"):
            self._build_properties()

        return self._type == TimeScope.Type.week

    @property
    def is_quarter(self) -> bool:
        if not hasattr(self, "_type"):
            self._build_properties()

        return self._type == TimeScope.Type.quarter

    @property
    def prev(self) -> Self:
        return TimeScopeBuilder.prev_scope(self)

    @property
    def next(self) -> Self:
        return TimeScopeBuilder.next_scope(self)

    @property
    def parent_week(self) -> Self:
        if self.is_day:
            return TimeScopeBuilder.get_parent_scope(self)

        raise ValueError(f"Couldn't find parent_week: {repr(self)}")

    @property
    def parent_quarter(self) -> Self:
        if self.is_day:
            parent_week = TimeScopeBuilder.get_parent_scope(self)
            parent_quarter = TimeScopeBuilder.get_parent_scope(parent_week)
            return parent_quarter

        elif self.is_week:
            return TimeScopeBuilder.get_parent_scope(self)

        raise ValueError(f"Couldn't find parent_quarter: {repr(self)}")

    @property
    def children(self):
        yield from TimeScopeBuilder.get_child_scopes(self)

    def as_short_str(self, reference_scope: Self | str) -> str:
        if reference_scope == self:
            return ""

        if reference_scope[0:4] != self[0:4]:
            return self

        return self[5:]

    def as_long_str(self) -> str:
        # Quarter scopes should have different formatting, because they're much weirder
        if self.is_quarter:
            return self + self.start.strftime(" // %b %d")

        return self + self.start.strftime("-%b-%d")


class TimeScopeBuilder:
    @staticmethod
    def day_scope_from_dt(dt: datetime) -> TimeScope:
        "Construct a \"day\" TimeScope, since datetimes are points in time"
        return TimeScope(dt.strftime("%G-ww%V.%u"))

    @staticmethod
    def prev_scope(scope: TimeScope) -> TimeScope:
        if not hasattr(scope, "_type"):
            scope._build_properties()

        if scope._type == TimeScope.Type.week:
            dt = scope.start + timedelta(days=-7)
            return TimeScope(dt.strftime(f"%G-ww%V"))

        elif scope._type == TimeScope.Type.day:
            dt = scope.start + timedelta(days=-1)
            return TimeScope(dt.strftime(f"%G-ww%V.%u"))

        elif scope._type == TimeScope.Type.quarter:
            m = re.fullmatch(r"(\d\d\d\d)—Q([1-4])", scope)
            if m and m[2] == '1':
                return TimeScope(f"{int(m[1]) - 1}—Q4")
            elif m:
                return TimeScope(f"{m[1]}—Q{int(m[2]) - 1}")

        raise ValueError(f"Couldn't calculate prev_scope for: {repr(scope)}")

    @staticmethod
    def next_scope(scope: TimeScope) -> TimeScope:
        if not hasattr(scope, "_type"):
            scope._build_properties()

        if scope._type == TimeScope.Type.week:
            return TimeScope(scope.end.strftime(f"%G-ww%V"))

        elif scope._type == TimeScope.Type.day:
            return TimeScope(scope.end.strftime(f"%G-ww%V.%u"))

        elif scope._type == TimeScope.Type.quarter:
            m = re.fullmatch(r"(\d\d\d\d)—Q([1-4])", scope)
            if m and m[2] == '4':
                return TimeScope(f"{int(m[1]) + 1}—Q1")
            elif m:
                return TimeScope(f"{m[1]}—Q{int(m[2]) + 1}")

        raise ValueError(f"Couldn't calculate next_scope for: {repr(scope)}")

    @staticmethod
    def get_parent_scope(scope: TimeScope) -> TimeScope | None:
        if scope.is_quarter:
            # Quarters return themselves because that makes client code a lot simpler.
            return scope

        elif scope.is_week:
            # NB Weeks can potentially be split across two quarters,
            # so use the ISO 8601 definition of calendar week and check Thursday.
            start_date = datetime.strptime(f'{scope}.4', '%G-ww%V.%u').date()

            start_quarter = (start_date.month - 1) // 3 + 1
            return TimeScope(f'{start_date.year}—Q{start_quarter}')

        elif scope.is_day:
            return TimeScope(scope[:9])

        return None

    @functools.lru_cache(maxsize=500)
    @staticmethod
    def get_child_scopes(scope: TimeScope) -> List[TimeScope]:
        if scope.is_day:
            return []

        elif scope.is_week:
            return [TimeScope(f"{scope}.{day}") for day in range(1, 8)]

        elif scope.is_quarter:
            result = []

            start_day = TimeScopeBuilder.day_scope_from_dt(scope.start)
            current_week = TimeScopeBuilder.get_parent_scope(start_day)

            while current_week.end <= scope.end:
                result.append(current_week)
                current_week = current_week.next

            return result

        raise ValueError(f"Couldn't calculate child scopes for: {repr(scope)}")
