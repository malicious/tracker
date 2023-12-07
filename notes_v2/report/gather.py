from datetime import datetime
from typing import Dict, List, Iterable

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload, query

from notes_v2.models import Note, NoteDomain
from notes_v2.time_scope import TimeScope

NOTES_KEY = "notes"


class NoteStapler:
    """
    Bundles up Note.as_json() results into a Jinja-renderable dict

    The only really hard part of this is the auto-promotion: if there
    aren't enough "day" tasks, they get bundled together into a "week"
    or "quarter" scope for ease of scanning.
    """

    def __init__(
            self,
            db_session: Session,
            domains_filter: Iterable[str],
            week_promotion_threshold: int,
            quarter_promotion_threshold: int,
    ):
        self.session = db_session

        domains_filter_sql = []
        if domains_filter:
            domains_filter_sql = [NoteDomain.domain_id.like(d + "%") for d in domains_filter]

        # TODO: Combining domain and scope filtering doesn't work, but it should
        self.filtered_query = (
            select(Note)
            .join(NoteDomain, Note.note_id == NoteDomain.note_id)
            .filter(or_(*domains_filter_sql))
            .options(joinedload(Note.domains))
            .group_by(Note)
        )

        self.scope_tree = {}
        # When larger scopes have a very low number of notes,
        # hide the <svg>'s and just render the notes directly,
        # because we usually don't care about the timing.
        self.week_promotion_threshold = week_promotion_threshold
        self.quarter_promotion_threshold = quarter_promotion_threshold

    def _construct_scope_tree(self, scope: TimeScope) -> Dict:
        # TODO: Could probably collapse these cases into something cute and recursive
        if scope.is_quarter():
            if scope not in self.scope_tree:
                self.scope_tree[scope] = {
                    NOTES_KEY: [],
                }

            return self.scope_tree[scope]

        elif scope.is_week():
            quarter_tree = self._construct_scope_tree(scope.parent)
            if scope not in quarter_tree:
                quarter_tree[scope] = {
                    NOTES_KEY: [],
                }

            return quarter_tree[scope]

        elif scope.is_day():
            week_tree = self._construct_scope_tree(scope.parent)
            if scope not in week_tree:
                week_tree[scope] = {
                    NOTES_KEY: [],
                }

            return week_tree[scope]

        raise ValueError(f"TimeScope has unknown type: {repr(scope)}")

    def _collapse_scope_tree(self, scope: TimeScope) -> None:
        scope_tree = self._construct_scope_tree(scope)

        for child in list(scope_tree.keys()):
            if child == NOTES_KEY:
                continue

            # NB this call depends on scope_tree being sorted correctly
            # (construct will do a lookup, rather than passing the child dict directly).
            # Not unreasonable, but this is the only time this is explicitly depended-on.
            self._collapse_scope_tree(child)

            scope_tree[NOTES_KEY].extend(
                scope_tree[child][NOTES_KEY]
            )
            del scope_tree[child]

        # TODO: Export this function as something shared/shareable
        def as_sort_time(n: Note) -> datetime:
            if n.sort_time:
                return n.sort_time

            ts = TimeScope(n.time_scope_id)
            if ts.is_day():
                return datetime.strptime(n.time_scope_id, "%G-ww%V.%u")
            elif ts.is_week():
                return datetime.strptime(n.time_scope_id + '.1', "%G-ww%V.%u")
            elif ts.is_quarter():
                start_year = int(ts[:4])
                start_month = int(ts[-1]) * 3 - 2
                return datetime(start_year, start_month, 1)
            else:
                raise ValueError("Unsortable Note.time_scope_id")

        scope_tree[NOTES_KEY].sort(key=as_sort_time)

    def _add_by_day(
            self,
            scope: TimeScope,
    ) -> int:
        new_note_rows = self.filtered_query \
            .filter(Note.time_scope_id == scope) \
            .order_by(Note.sort_time.asc())
        new_notes = list(n for (n,) in self.session.execute(new_note_rows).unique().all())

        notes_list = self._construct_scope_tree(scope)[NOTES_KEY]
        notes_list.extend(new_notes)
        return len(new_notes)

    def _add_by_week(
            self,
            scope: TimeScope,
            skip_child_scopes: bool = False,
    ) -> int:
        total_notes_count = 0
        if not skip_child_scopes:
            for day_scope in scope.child_scopes:
                added_notes = self._add_by_day(TimeScope(day_scope))
                total_notes_count += added_notes

        new_note_rows = self.filtered_query \
            .filter(Note.time_scope_id == scope) \
            .order_by(Note.time_scope_id.asc())
        new_notes = list(n for (n,) in self.session.execute(new_note_rows).unique().all())

        notes_list = self._construct_scope_tree(scope)[NOTES_KEY]
        notes_list.extend(new_notes)
        total_notes_count += len(new_notes)

        # Now, for the auto-promotion if child scopes aren't numerous enough
        if total_notes_count <= self.week_promotion_threshold:
            self._collapse_scope_tree(scope)

        return total_notes_count

    def _add_by_quarter(
            self,
            scope: TimeScope,
            skip_child_scopes: bool = False,
    ) -> int:
        total_notes_count = 0
        if not skip_child_scopes:
            for week_scope in scope.child_scopes:
                added_notes = self._add_by_week(TimeScope(week_scope), skip_child_scopes)
                total_notes_count += added_notes

        new_note_rows = self.filtered_query \
            .filter(Note.time_scope_id == scope) \
            .order_by(Note.time_scope_id.asc())
        new_notes = list(n for (n,) in self.session.execute(new_note_rows).unique().all())

        notes_list = self._construct_scope_tree(scope)[NOTES_KEY]
        notes_list.extend(new_notes)
        total_notes_count += len(new_notes)

        if total_notes_count <= self.quarter_promotion_threshold:
            self._collapse_scope_tree(scope)

        return total_notes_count

    def add_by_scope(self, scope: TimeScope) -> None:
        if scope.is_quarter():
            self._add_by_quarter(scope)
        elif scope.is_week():
            # Add notes in reverse order, because _collapse_scope_tree() reasons
            self._add_by_quarter(scope.get_parent(), skip_child_scopes=True)
            self._add_by_week(scope)
        elif scope.is_day():
            # Add notes in reverse order, because _collapse_scope_tree() reasons
            self._add_by_quarter(scope.get_parent().get_parent(), skip_child_scopes=True)
            self._add_by_week(scope.get_parent(), skip_child_scopes=True)
            self._add_by_day(scope)
        else:
            raise ValueError(f"TimeScope has unknown type: {repr(scope)}")

    def add_everything(self) -> None:
        new_note_rows = self.filtered_query
        new_notes = list(n for (n,) in self.session.execute(new_note_rows).unique().all())

        for n in new_notes:
            note_list = self._construct_scope_tree(TimeScope(n.time_scope_id))[NOTES_KEY]
            note_list.append(n)

        # Once we're done, iteratively check if we need to do collapsing
        for quarter in list(self.scope_tree.keys()):
            quarter_count = 0

            for week in list(self.scope_tree[quarter].keys()):
                week_count = 0

                # If this isn't a real week, but the quarter's notes:
                if week == NOTES_KEY:
                    quarter_count += len(self.scope_tree[quarter][week])
                    continue

                for day in list(self.scope_tree[quarter][week].keys()):
                    # If this isn't a real day, but the week's notes:
                    if day == NOTES_KEY:
                        week_count += len(self.scope_tree[quarter][week][day])
                        continue

                    week_count += len(self.scope_tree[quarter][week][day][NOTES_KEY])

                if week_count <= self.week_promotion_threshold:
                    self._collapse_scope_tree(week)
                if week_count == 0:
                    raise RuntimeError(f"ERROR: somehow, we created an empty week-scope {week}")

                quarter_count += week_count

            if quarter_count <= self.quarter_promotion_threshold:
                self._collapse_scope_tree(quarter)
            if quarter_count == 0:
                raise RuntimeError(f"ERROR: somehow, we created an empty quarter-scope {quarter}")


def notes_json_tree(
        db_session: Session,
        domain_ids: Iterable[str],
        scope_ids: Iterable[str],
        disable_scope_collapse: bool = False,
):
    week_promotion_threshold: int = 9
    quarter_promotion_threshold: int = 17
    if disable_scope_collapse:
        week_promotion_threshold = 0
        quarter_promotion_threshold = 0

    ns = NoteStapler(
        db_session,
        domain_ids,
        week_promotion_threshold,
        quarter_promotion_threshold,
    )

    for scope_id in scope_ids:
        ns.add_by_scope(TimeScope(scope_id))

    if not scope_ids:
        ns.add_everything()

    return ns.scope_tree
