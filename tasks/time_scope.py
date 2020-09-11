import re
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Dict


class TimeScope(str):
    class Type(Enum):
        week = 7
        day = 1
        quarter = 90

    def __new__(cls, scope_str: str):
        if scope_str[0:2] == "ww":
            scope_str = f"{date.today().year}-{scope_str}"

        return str.__new__(cls, scope_str)

    def get_type(self) -> Type:
        if not hasattr(self, "_type"):
            self._parse_derived_properties()

        return self._type

    def get_start(self) -> datetime:
        if not hasattr(self, "_start"):
            self._parse_derived_properties()

        return self._start

    def get_end(self) -> datetime:
        if not hasattr(self, "_end"):
            self._parse_derived_properties()

        return self._end

    type = property(get_type)
    start = property(get_start)
    end = property(get_end)

    def _parse_derived_properties(self):
        """
        Provides support for a custom time-scope format used in my notes

        - days are canonically specified as: `2020-ww35.5`
        - weeks as: `2020-ww35`
        - quarters as: `2020—Q3` (note that that is an em dash)
        """

        def dt_from_iso(year, week, weekday) -> datetime:
            "This already exists in datetime 3.8+"
            return datetime.strptime(f'{year} {week} {weekday}', '%G %V %u')

        m = re.fullmatch(r"(\d\d\d\d)-ww([0-5]\d)", self)
        if m:
            self._type = TimeScope.Type.week
            self._start = dt_from_iso(m[1], m[2], 1)
            self._end = self._start + timedelta(days=7)
            return

        m = re.fullmatch(r"(\d\d\d\d)-ww([0-5]\d)\.(\d)", self)
        if m:
            self._type = TimeScope.Type.day
            self._start = dt_from_iso(m[1], m[2], m[3])
            self._end = self._start + timedelta(days=1)
            return

        m = re.fullmatch(r"(\d\d\d\d)—Q([1-4])", self)
        if m:
            self._type = TimeScope.Type.quarter
            year = int(m[1])
            if m[2] == '1':
                self._start = datetime(year, 1, 1)
                self._end = datetime(year, 4, 1)
            elif m[2] == '2':
                self._start = datetime(year, 4, 1)
                self._end = datetime(year, 7, 1)
            elif m[2] == '3':
                self._start = datetime(year, 7, 1)
                self._end = datetime(year, 10, 1)
            elif m[2] == '4':
                self._start = datetime(year, 10, 1)
                self._end = datetime(year + 1, 1, 1)
            return

        raise ValueError(f"Couldn't parse TimeScope: {repr(self)}")

    def to_json_dict(self) -> Dict:
        return {
            "self": self,
            "type": str(self.type),
            "start": str(self.start),
            "end": str(self.end),
        }

    def shorten(self, reference_scope) -> str:
        if reference_scope[0:4] != self[0:4]:
            return self
        elif reference_scope != self:
            return self[5:]
        else:
            return ""
