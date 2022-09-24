import re
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional


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

    def __new__(cls, scope_str: str):
        # If we skipped the year prefix on the scope, assume it's this year
        if scope_str[0:2] == "ww":
            scope_str = f"{date.today().year}-{scope_str}"

        return str.__new__(cls, scope_str)

    def is_quarter(self) -> bool:
        m = re.fullmatch(r"(\d\d\d\d)—Q([1-4])", self)
        return m is not None

    def is_week(self) -> bool:
        m = re.fullmatch(r"(\d\d\d\d)-ww([0-5]\d)", self)
        return m is not None

    def is_day(self) -> bool:
        m = re.fullmatch(r"(\d\d\d\d)-ww([0-5]\d)\.(\d)", self)
        return m is not None

    # TODO: Function spec should be Optional[TimeScope]
    def get_parent(self) -> Optional[str]:
        if self.is_quarter():
            return None

        elif self.is_week():
            # NB weeks can technically belong to two quarters; use the _earlier_
            # quarter, due to `notes-v2.html` rendering (specifically, later
            # dates appear first, so an extra "early" quarter isn't noticeable
            # until you've scrolled through the whole list).
            #
            start_date = datetime.strptime(f'{self}.1', '%G-ww%V.%u').date()
            start_quarter = (start_date.month - 1) // 3 + 1
            return TimeScope(f'{start_date.year}—Q{start_quarter}')

        elif self.is_day():
            return TimeScope(self[:9])

        raise ValueError(f"TimeScope has unknown type: {repr(self)}")

    parent = property(get_parent)

    def get_child_scopes(self) -> List[str]:
        if self.is_quarter():
            start_year = int(self[:4])
            start_month = int(self[-1]) * 3 - 2

            # Find the start and end dates for the quarter
            start_date = datetime(start_year, start_month, 1)
            if start_month == 10:
                end_date = datetime(start_year+1, 1, 1)
            else:
                # end_date is one-past-the-end, so the first of the month is expected
                end_date = datetime(start_year, start_month+3, 1)

            # Iterate over all weeks
            all_weeks = []
            child_date = start_date
            while child_date < end_date:
                child_scope = TimeScope(child_date.strftime(f'%G-ww%V'))
                # TODO: We should have a less… expensive way of eliminating overlap,
                #       but this method allows us to consolidate the duplicate-checking
                #       into a single function (TimeScope.get_parent)
                if child_scope.get_parent() != self:
                    print(f"WARN: generated child scope {child_scope} that isn't 1:1 with expected parent {self}")
                    child_date = child_date + timedelta(days=7)
                    continue

                all_weeks.append(child_scope)
                child_date = child_date + timedelta(days=7)

            return all_weeks

        elif self.is_week():
            return [f'{self}.{day}' for day in range(1, 8)]

        elif self.is_day():
            return []

    child_scopes = property(get_child_scopes)

    @classmethod
    def from_datetime(cls, dt):
        "Construct a \"day\" TimeScope, since datetimes are points in time"
        return cls(dt.strftime("%G-ww%V.%u"))

    def minimize_vs(self, ref_scope) -> str:
        if ref_scope == self:
            return ""

        # If the years are different, there's nothing to minimize
        if ref_scope[0:4] != self[0:4]:
            return self

        return self[5:]
