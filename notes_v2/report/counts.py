from dataclasses import dataclass
from datetime import datetime
from typing import Tuple

from flask import render_template, url_for
from markupsafe import Markup
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import Session

from .render_utils import render_cache, render_cache_generator
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
    @render_cache_generator('calendar quarters', (), (page_domain_filter,))
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

    @render_cache_generator('calendar single', page_domain_filter)
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
        page_domains: Tuple[str],
        page_domain_filters: Tuple[str],
):
    @render_cache_generator('calendar quarters', page_domains, page_domain_filters)
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

        # These have to be provided in one shot to be OR'd,
        # providing them in two .where() clauses generates an AND.
        where_clauses = [
            *[NoteDomain.domain_id.ilike(f) for f in page_domains],
            *[NoteDomain.domain_id.ilike(f) for f in page_domain_filters],
        ]

        if len(where_clauses) > 1:
            scope_bounds_query = scope_bounds_query.where(or_(*where_clauses))
        elif len(where_clauses) == 1:
            scope_bounds_query = scope_bounds_query.where(where_clauses[0])

        scope_bounds = db_session.execute(scope_bounds_query).one()
        if not scope_bounds[0] or not scope_bounds[1]:
            raise ValueError(f"Couldn't find any TimeScope boundaries for {page_domains} + {page_domain_filters}")

        current_quarter = TimeScope(scope_bounds[0]).parent_quarter
        end_end: datetime = TimeScope(scope_bounds[1]).end
        while current_quarter.start < end_end:
            yield current_quarter
            current_quarter = current_quarter.next

    @dataclass
    class GenerationResult:
        quarter_ignored: int = 0
        week_ignored: int = 0
        entries_modified: int = 0
        "Counts the number of entries modified, so we can skip rendering if 0"

    @render_cache_generator('calendar multi', page_domains, page_domain_filters)
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
        initialized_domains = set()
        result = GenerationResult()

        for week in quarter_scope.children:
            per_week_counts[week] = {}

        def fetch_per_domain_counts(
                domain_filter: str,
                coalesce_matching_domains: bool = False,
        ) -> None:
            if domain_filter in initialized_domains:
                return

            if coalesce_matching_domains:
                base_query = \
                    select(Note.time_scope_id, func.count(Note.note_id)) \
                    .group_by(Note.time_scope_id)
            else:
                base_query = \
                    select(Note.time_scope_id, func.count(Note.note_id), NoteDomain.domain_id) \
                    .group_by(Note.time_scope_id, NoteDomain.domain_id)

            count_rows = db_session.execute(
                base_query
                .join(NoteDomain, NoteDomain.note_id == Note.note_id)
                .where(and_(
                    NoteDomain.domain_id.ilike(domain_filter),
                    Note.time_scope_id >= TimeScopeBuilder.day_scope_from_dt(quarter_scope.start),
                    Note.time_scope_id < TimeScopeBuilder.day_scope_from_dt(quarter_scope.end),
                ))
                .order_by(
                    Note.time_scope_id.asc(),
                )
            ).all()

            for count_row in count_rows:
                count_scope = TimeScope(count_row[0])
                if not count_scope.is_day:
                    if count_scope.is_quarter:
                        result.quarter_ignored += 1
                    if count_scope.is_week:
                        result.week_ignored += 1
                    continue

                if coalesce_matching_domains:
                    domain_ish_label = str(domain_filter)
                else:
                    domain_ish_label = count_row[2]

                # TODO: This will be inconsistent across quarters, but is that okay?
                if domain_ish_label not in initialized_domains:
                    for counts in per_week_counts.values():
                        counts[domain_ish_label] = [0] * 7
                    initialized_domains.add(domain_ish_label)

                week_counts = per_week_counts[count_scope.parent_week]
                day_index = int(count_scope[-1]) - 1
                week_counts[domain_ish_label][day_index] = count_row[1]

                result.entries_modified += 1

        for domain_filter in page_domain_filters:
            fetch_per_domain_counts(domain_filter, True)

        for domain in page_domains:
            fetch_per_domain_counts(domain)

        if not result.entries_modified:
            return []

        # Now that everything's populated appropriately, return the results
        yield from per_week_counts.items()

    @render_cache
    def link_filter(scope: TimeScope, domain_filter):
        url = url_for(
            ".do_render_matching_notes",
            scope=scope,
            domain=domain_filter,
        )
        response = f'<a href="{url}">{domain_filter}</a>'
        return Markup(response)

    @render_cache
    def link_scope(scope: TimeScope):
        url = url_for(
            ".do_render_matching_notes",
            scope=scope,
            domain=(*page_domains, *page_domain_filters),
        )
        response = f'<a href="{url}">{scope.as_long_str()}</a>'
        return Markup(response)

    # NB This is apparently very bad to cache. Maybe it's the decorator overhead?
    def is_future(scope: TimeScope):
        dt0 = datetime.now()  # TODO: Decide what to do with timezones
        return dt0 < scope.start

    return render_template(
        'notes/counts.html',
        make_quarters=quarters_generator,
        make_counts=counts_generator,
        link_scope=link_scope,
        link_filter=link_filter,
        is_future=is_future,
    )
