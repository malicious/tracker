from typing import Dict, List

from sqlalchemy import or_

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

    def __init__(self, domains_filter: List[str]):
        self.filtered_query = Note.query
        if domains_filter:
            domains_filter_sql = [NoteDomain.domain_id.like(d + "%") for d in domains_filter]
            # TODO: Combining domain and scope filtering doesn't work
            # TODO: Need to close the session object for the queries we run
            self.filtered_query = self.filtered_query \
                .join(NoteDomain, Note.note_id == NoteDomain.note_id) \
                .filter(or_(*domains_filter_sql))

        self.scope_tree = {}
        # because week can be week-summary + 7 day-summaries
        self.week_promotion_threshold = 9
        self.quarter_promotion_threshold = 17

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

    def _add_by_day(self, scope: TimeScope) -> int:
        new_notes = list(self.filtered_query
                         .filter(Note.time_scope_id == scope)
                         .order_by(Note.sort_time.asc())
                         .all())

        notes_list = self._construct_scope_tree(scope)[NOTES_KEY]
        notes_list.extend(new_notes)
        return len(new_notes)

    def _add_by_week(self, scope: TimeScope) -> int:
        total_notes_count = 0
        for day_scope in scope.child_scopes:
            added_notes = self._add_by_day(TimeScope(day_scope))
            total_notes_count += added_notes

        new_notes = list(self.filtered_query
                         .filter(Note.time_scope_id == scope)
                         .order_by(Note.time_scope_id.asc())
                         .all())

        notes_list = self._construct_scope_tree(scope)[NOTES_KEY]
        notes_list.extend(new_notes)
        total_notes_count += len(new_notes)

        # Now, for the auto-promotion if child scopes aren't numerous enough
        if total_notes_count <= self.week_promotion_threshold:
            self._collapse_scope_tree(scope)

        return total_notes_count

    def _add_by_quarter(self, scope: TimeScope) -> int:
        total_notes_count = 0
        for week_scope in scope.child_scopes:
            added_notes = self._add_by_week(TimeScope(week_scope))
            total_notes_count += added_notes

        new_notes = list(self.filtered_query
                         .filter(Note.time_scope_id == scope)
                         .order_by(Note.time_scope_id.asc())
                         .all())

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
            self._add_by_week(scope)
        elif scope.is_day():
            self._add_by_day(scope)
        else:
            raise ValueError(f"TimeScope has unknown type: {repr(scope)}")

    def add_everything(self) -> None:
        notes = self.filtered_query.all()
        for n in notes:
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


def notes_json_tree(domains: List[str], scope_ids: List[str]):
    ns = NoteStapler(domains_filter=domains)

    for scope_id in scope_ids:
        ns.add_by_scope(TimeScope(scope_id))

    if not scope_ids:
        ns.add_everything()

    return ns.scope_tree
