from typing import Tuple

from flask import render_template
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import Session

from ..models import NoteDomain, Note
from util import TimeScope, TimeScopeBuilder


def calendar(
        db_session: Session,
        page_scopes: Tuple[str],
        page_domain_filters: Tuple[str],
):
    query = (
        select(
            NoteDomain.domain_id,
            Note.time_scope_id,
            func.count(Note.note_id),
        )
        .join(NoteDomain, NoteDomain.note_id == Note.note_id)
        .group_by(NoteDomain.domain_id, Note.time_scope_id)
        .order_by(
            NoteDomain.domain_id.desc(),
            func.count(Note.note_id).desc(),
        )
    )

    if page_domain_filters:
        query = query.where(or_(
            *[NoteDomain.domain_id.ilike(filter) for filter in page_domain_filters],
        ))
    if page_scopes:
        query = query.filter(Note.time_scope_id.in_(page_scopes))

    response_json = {}
    "Maps from domain_id to {scope: count}"

    for stats_row in db_session.execute(query).all():
        domain_info = response_json.get(stats_row[0], {})
        domain_info[stats_row[1]] = stats_row[2]

        response_json[stats_row[0]] = domain_info

    return response_json


def render_one_calendar(
        db_session: Session,
        page_domain_filter: str,
):
    def quarters_generator():
        scope_bounds_query = (
            select(
                func.min(Note.time_scope_id),
                func.max(Note.time_scope_id),
            )
            .join(NoteDomain, NoteDomain.note_id == Note.note_id)
            .where(NoteDomain.domain_id.ilike(page_domain_filter))
            .filter(func.not_(Note.time_scope_id.contains('—')))
        )

        scope_bounds = db_session.execute(scope_bounds_query).one()

        current_quarter = TimeScope(scope_bounds[0]).parent_quarter
        end_end: datetime = TimeScope(scope_bounds[1]).end
        while current_quarter.start < end_end:
            yield current_quarter
            current_quarter = current_quarter.next

    def day_counts_generator(quarter_scope: TimeScope):
        per_week_counts = {}
        for week in quarter_scope.children:
            per_week_counts[week] = [0] * 7

        query = (
            select(
                Note.time_scope_id,
                func.count(Note.note_id),
            )
            .join(NoteDomain, NoteDomain.note_id == Note.note_id)
            .where(and_(
                NoteDomain.domain_id.ilike(page_domain_filter),
                # NB These are string comparisons!
                Note.time_scope_id >= TimeScopeBuilder.day_scope_from_dt(quarter_scope.start),
                Note.time_scope_id < TimeScopeBuilder.day_scope_from_dt(quarter_scope.end),
            ))
            .group_by(Note.time_scope_id)
            .order_by(
                Note.time_scope_id.asc(),
            )
        )

        for count_row in db_session.execute(query).all():
            count_scope = TimeScope(count_row[0])
            if not count_scope.is_day:
                continue

            week_counts = per_week_counts[count_scope.parent_week]
            day_index = int(count_scope[-1]) - 1
            week_counts[day_index] = count_row[1]

        # Now that everything's populated appropriately, return the results
        yield from per_week_counts.items()

    def week_counts_generator(quarter_scope: TimeScope):
        for week_scope, day_counts in day_counts_generator(quarter_scope):
            yield week_scope, len([c for c in day_counts if c])

    return render_template(
        'notes/counts-simple.html',
        make_quarters=quarters_generator,
        make_week_counts=week_counts_generator,
        make_day_counts=day_counts_generator,
    )


def render_calendar(
        db_session: Session,
        page_domain_filters: Tuple[str],
):
    def quarters_generator():
        """
        This function is a little dumb because time_scope_id's are stored dumbly in SQLite.
        Specifically, the emdash of a "quarter" scope will always come last.

        So rather than try to sort it out, just filter out emdashes.
        """
        scope_bounds_query = (
            select(
                func.min(Note.time_scope_id),
                func.max(Note.time_scope_id),
            )
            .join(NoteDomain, NoteDomain.note_id == Note.note_id)
            .filter(func.not_(Note.time_scope_id.contains('—')))
        )

        if len(page_domain_filters) > 1:
            scope_bounds_query = scope_bounds_query \
                .where(or_(*[NoteDomain.domain_id.ilike(f) for f in page_domain_filters]))
        elif len(page_domain_filters) == 1:
            scope_bounds_query = scope_bounds_query \
                .where(NoteDomain.domain_id.ilike(page_domain_filters[0]))

        scope_bounds = db_session.execute(scope_bounds_query).one()

        current_quarter = TimeScope(scope_bounds[0]).parent_quarter
        end_end: datetime = TimeScope(scope_bounds[1]).end
        while current_quarter.start < end_end:
            yield current_quarter
            current_quarter = current_quarter.next

        return

    def counts_generator(quarter_scope: TimeScope):
        per_week_counts = {}
        """
        nested dict mapping from weeks to domains to counts:

            {
                "2024-ww39": {
                    "type: summary": [0, 0, 0, 0, 0, 0, 0],
                    "dietary%": [1, 2, 1, 2, 13, 0, 0]
                }
            }
        """
        entries_modified: int = 0
        "Counts the number of entries modified, so we can skip rendering if 0"

        for week in quarter_scope.children:
            per_week_counts[week] = {}

        for domain_filter in page_domain_filters:
            # Initialize all the counts for this filter.
            for counts in per_week_counts.values():
                counts[domain_filter] = [0] * 7

            query = (
                select(
                    Note.time_scope_id,
                    func.count(Note.note_id),
                )
                .join(NoteDomain, NoteDomain.note_id == Note.note_id)
                .where(and_(
                    NoteDomain.domain_id.ilike(domain_filter),
                    # NB These are string comparisons!
                    Note.time_scope_id >= TimeScopeBuilder.day_scope_from_dt(quarter_scope.start),
                    Note.time_scope_id < TimeScopeBuilder.day_scope_from_dt(quarter_scope.end),
                ))
                .group_by(Note.time_scope_id)
                .order_by(
                    Note.time_scope_id.asc(),
                )
            )

            for count_row in db_session.execute(query).all():
                count_scope = TimeScope(count_row[0])
                if not count_scope.is_day:
                    continue

                week_counts = per_week_counts[count_scope.parent_week]
                day_index = int(count_scope[-1]) - 1
                week_counts[domain_filter][day_index] = count_row[1]

                entries_modified += 1

        if not entries_modified:
            return []

        # Now that everything's populated appropriately, return the results
        yield from per_week_counts.items()

    return render_template(
        'notes/counts.html',
        make_quarters=quarters_generator,
        make_counts=counts_generator,
    )
