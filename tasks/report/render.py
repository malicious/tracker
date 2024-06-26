from dataclasses import dataclass
from datetime import timedelta, date
from typing import Iterable, Callable

from markupsafe import escape
from sqlalchemy import exists
from sqlalchemy.orm import Session

from tasks.database_models import TaskLinkage, Task
from util import TimeScope


def _to_aio(t) -> Iterable[str]:
    yield f"{t.desc}\n\n"
    for tl in t.linkages:
        yield f"## {tl.time_scope_id}"
        if tl.resolution:
            yield f" | {tl.resolution}"
        yield "\n"
        if tl.detailed_resolution:
            # This is a little too hard-coded to the way I personally do notes,
            # but given that the output format has markdown datetime-comments, it's fine.
            if tl.detailed_resolution[:5] != '<!-- ':
                # NB we only support millisecond precision in generation,
                # but the SQLite backing store upgrades everything to microseconds.
                yield f"<!-- {tl.created_at.strftime('%G-ww%V.%u %H:%M:%S.%f')} -->\n"
            yield tl.detailed_resolution
            yield "\n"
        yield "\n"


def to_aio(t):
    # TODO: Determine whether escape() will make this an O(n^2) operation.
    return escape(''.join(_to_aio(t)))


def render_scope(task_date, section_date):
    max_task_age = 100

    # Clamp the color intensity to [0,100] days
    section_date_str = section_date.strftime("%G-ww%V.%u")
    days_old = (section_date - task_date).days
    if days_old == 0:
        # For due-today tasks, don't render a scope at all
        return ''

    # Scale the colors from grey to reddish
    color_intensity = min(max_task_age, max(days_old, 0)) / 100.0
    color_rgb = (200 + 25 * color_intensity,
                 200 - 100 * color_intensity,
                 200 - 100 * color_intensity)

    # If the year is the same, render as "ww06.5"
    short_date_str = task_date.strftime("%G-ww%V.%u")
    if short_date_str[0:5] == section_date_str[0:5]:
        short_date_str = short_date_str[5:]

    return (
        '<span class="task-scope" '
        f'style="color: rgb({color_rgb[0]}, {color_rgb[1]}, {color_rgb[2]})">'
        f'{short_date_str}'
        '</span>'
    )


@dataclass
class TaskRenderInfo:
    scope_to_print: str
    resolution_to_print: str | None
    is_future_task: bool
    is_readonly_import_source: bool


def make_renderer(
        db_session: Session,
        todays_date: date,
        is_readonly_import_source: Callable[[str], bool],
) -> Callable[[Task], TaskRenderInfo]:
    """
    Provides enough info for Jinja template to render the task

    Task "status" is complicated, in this case in UI terms.
    To represent it cleanly, we perform an "expensive" calculation,
    and expect the caller to cache these results.

    Inputs:

    - whether there is a reference scope (sometimes we just want to list every task)
    - whether there's a TaskLinkage attached to that reference scope
    - whether there's more than one TaskLinkage
    - whether there's more than one _open_ TaskLinkage
    - whether the TaskLinkages are in the future

    - if there's only one linkage, and it's open, show nothing
    - if there's only one linkage and it's resolved, indicate it's resolved
    - for multiple linkages:
      - if only one is open...

    Returns a function that returns a tuple of (scope to print, resolution to print, is future task)
    """

    def minimize_vs_today(printed_scope_id) -> str:
        todays_scope_id = todays_date.strftime("%G-ww%V.%u")
        return TimeScope(printed_scope_id).as_short_str(todays_scope_id)

    def _compute(t: Task) -> TaskRenderInfo:
        open_linkages_exist = db_session.scalar(
            exists()
            .where(
                TaskLinkage.task_id.is_(t.task_id),
                TaskLinkage.import_source.is_(t.import_source),
                TaskLinkage.resolution.is_(None),
            )
            .select()
        )
        # If every linkage is closed, just return the "last" resolution
        if not open_linkages_exist:
            return TaskRenderInfo('', t.linkages[-1].resolution, False, is_readonly_import_source(t.import_source))

        # By this point multiple linkages exist, but at least one is open
        latest_open = [tl for tl in t.linkages if not tl.resolution][-1]
        if latest_open.time_scope - todays_date > timedelta(days=3):
            return TaskRenderInfo(minimize_vs_today(latest_open.time_scope_id), None, True,
                                  is_readonly_import_source(t.import_source))
        elif latest_open.time_scope > todays_date:
            return TaskRenderInfo(minimize_vs_today(latest_open.time_scope_id), None, False,
                                  is_readonly_import_source(t.import_source))
        else:
            # TODO: past-tasks are the only ones that get their scope shrunken
            rendered_scope = render_scope(latest_open.time_scope, todays_date)
            return TaskRenderInfo(rendered_scope, None, False, is_readonly_import_source(t.import_source))

    return _compute
