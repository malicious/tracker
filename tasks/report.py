import json
import operator
import re
from collections import defaultdict
from datetime import datetime, timedelta
from textwrap import indent
from typing import Iterable, Optional

from flask import render_template, url_for, make_response
from markupsafe import escape
from sqlalchemy import or_, select, and_, func
from sqlalchemy.orm import Session

from .database_models import Task, TaskLinkage
from .time_scope import TimeScope, TimeScopeUtils


def to_summary_html(t: Task, ref_scope: Optional[TimeScope] = None) -> str:
    response_html = ""
    response_html += f'\n<span class="desc">{t.desc}</span>'
    response_html += f'\n<span class="task-id"><a href="{url_for(".get_task", task_id=t.task_id)}">#{t.task_id}</a></span>'

    tl_exact = None

    # If we have a ref_scope, try to print out its specific TaskLinkage
    if ref_scope:
        matching_linkages = [tl for tl in t.linkages if tl.time_scope_id == ref_scope]
        if len(matching_linkages) == 1:
            tl_exact = list(matching_linkages)[0]

    if tl_exact and tl_exact.resolution:
        return \
                '<summary class="task-resolved">\n' + \
                f'<span class="resolution">({tl_exact.resolution}) </span>' + \
                response_html + '\n' + \
                '</summary>'

    # Otherwise, do our best to guess at additional info
    short_scope_str = t.linkages[0].time_scope_id.strftime("%G-ww%V.%u")
    if short_scope_str[0:5] == ref_scope[0:5]:
        short_scope_str = short_scope_str[5:]

    return \
            '<summary class="task">' + \
            f'<span class="time-scope">{short_scope_str}</span>' + \
            response_html + '\n' + \
            '</summary>'


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


def report_one_task(task_id, return_bare_dict=False):
    task: Task = Task.query \
        .filter(Task.task_id == task_id) \
        .one_or_none()
    if not task:
        return {"error": f"invalid task_id: {task_id}"}

    if return_bare_dict:
        return task.as_json_dict()

    return f'<html><body><pre>{task.as_json()}</pre></body></html>'


def generate_tasks_by_scope(db_session: Session, scope_id: str):
    # day-like scope (`%G-ww%V.%u`)
    m = re.fullmatch(r"(\d\d\d\d)-ww([0-5]\d).(\d)", scope_id)
    if m:
        scope = datetime.strptime(scope_id, "%G-ww%V.%u").date()
        tasks = Task.query \
            .join(TaskLinkage,
                  and_(Task.task_id == TaskLinkage.task_id,
                       Task.import_source == TaskLinkage.import_source)) \
            .filter(TaskLinkage.time_scope == scope) \
            .order_by(TaskLinkage.time_scope, Task.category) \
            .all()

        return {
            scope_id: tasks,
        }

    # week-like scope (`%G-ww%V`)
    m = re.fullmatch(r"(\d\d\d\d)-ww([0-5]\d)", scope_id)
    if m:
        tasks_by_scope = {}

        for day in range(1, 8):
            day_scope_id = f"{scope_id}.{day}"
            day_scope = datetime.strptime(day_scope_id, "%G-ww%V.%u").date()
            tasks = Task.query \
                .join(TaskLinkage,
                      and_(Task.task_id == TaskLinkage.task_id,
                           Task.import_source == TaskLinkage.import_source)) \
                .filter(TaskLinkage.time_scope == day_scope) \
                .order_by(TaskLinkage.time_scope, Task.category) \
                .all()

            tasks_by_scope[day_scope_id] = tasks

        return tasks_by_scope

    # quarter-like scope (`YYYY—QN`, that's an emdash in the middle)
    m = re.fullmatch(r"(\d\d\d\d)—Q([1-4])", scope_id)
    if m:
        start_year = int(scope_id[:4])
        start_month = int(scope_id[-1]) * 3 - 2

        quarter_start_date = datetime(start_year, start_month, 1)
        if start_month == 10:
            quarter_end_date = datetime(start_year + 1, 1, 1)
        else:
            quarter_end_date = datetime(start_year, start_month + 3, 1)

        tasks_by_scope = {}

        current_day_start = quarter_start_date
        while current_day_start < quarter_end_date:
            tasks = Task.query \
                .join(TaskLinkage,
                      and_(Task.task_id == TaskLinkage.task_id,
                           Task.import_source == TaskLinkage.import_source)) \
                .filter(TaskLinkage.time_scope == current_day_start.date()) \
                .order_by(TaskLinkage.time_scope, Task.category) \
                .all()

            tasks_by_scope[current_day_start.strftime("%G-ww%V.%u")] = tasks
            current_day_start = current_day_start + timedelta(days=1)

        return tasks_by_scope

    # otherwise, no idea
    raise ValueError(f"No idea how to handle {repr(scope_id)}")


def fetch_tasks_by_domain(
        db_session: Session,
        query_limiter,
):
    # Fetch the final list of tasks; duplicate according to domain-ish splits.
    tasks_by_domain = defaultdict(set)

    query = query_limiter(
        select(Task)
        # TODO: Need to figure out a way to do time-sorting
        .order_by(Task.category)
    )
    task_rows = db_session.execute(query).all()

    for (task,) in task_rows:
        domains = ['']
        if task.category is not None and task.category.strip():
            # NB: No double-ampersands supported, because…
            #     too lazy to figure out how to share code with `notes_v2.add.tokenize_domain_ids()`
            domains = [d.strip() for d in task.category.strip().split('&')]

        for d in domains:
            tasks_by_domain[d].add(task)

    # Create a sorted version of this, for non-jumpy rendering.
    # TODO: This should be doable with an SQLAlchemy-level sort.
    sorted_tbd = {}
    for domain in sorted(tasks_by_domain.keys()):
        def sort_time(t: Task):
            return (
                max(map(operator.attrgetter('time_scope'), t.linkages)),
                t.task_id,
            )

        tasks = list(tasks_by_domain[domain])
        sorted_tbd[domain] = sorted(tasks, key=sort_time, reverse=True)

    return sorted_tbd


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


def compute_ignoring_scope(todays_date):
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
        if todays_scope_id == printed_scope_id:
            return ''

        # If the years are different, there's nothing to minimize
        if todays_scope_id[0:4] != printed_scope_id[0:4]:
            return printed_scope_id

        return printed_scope_id[5:]

    def _compute(t):
        # TODO: import the db session and use exists()/scalar()
        open_linkages_exist = TaskLinkage.query \
            .filter_by(task_id=t.task_id, resolution=None) \
            .all()
        # If every linkage is closed, just return the "last" resolution
        if not open_linkages_exist:
            return '', t.linkages[-1].resolution, False

        # By this point multiple linkages exist, but at least one is open
        latest_open = [tl for tl in t.linkages if not tl.resolution][-1]
        if latest_open.time_scope - todays_date > timedelta(days=3):
            return minimize_vs_today(latest_open.time_scope_id), None, True
        elif latest_open.time_scope > todays_date:
            return minimize_vs_today(latest_open.time_scope_id), None, False
        else:
            # TODO: past-tasks are the only ones that get their scope shrunken
            rendered_scope = render_scope(latest_open.time_scope, todays_date)
            return rendered_scope, None, False

    return _compute


# NB the arguments are kinda weird and inconsistent because they're default-false
#
def edit_tasks_all(
        db_session: Session,
        show_resolved: bool,
        hide_future: bool,
):
    render_kwargs = {}
    # Use the server's local time for rendering
    render_scope_dt = datetime.now()
    render_scope = TimeScope(render_scope_dt.strftime("%G-ww%V.%u"))

    render_time_dt = datetime.utcnow()
    recent_tasks_cutoff = render_time_dt - timedelta(hours=12)
    future_tasks_cutoff = render_time_dt + timedelta(days=32)

    def query_limiter(query):
        if show_resolved:
            return query

        elif hide_future:
            return query \
                .join(TaskLinkage,
                      and_(Task.task_id == TaskLinkage.task_id,
                           Task.import_source == TaskLinkage.import_source)) \
                .filter(or_(TaskLinkage.resolution == None,
                            TaskLinkage.created_at > recent_tasks_cutoff)) \
                .filter(TaskLinkage.time_scope < future_tasks_cutoff)

        else:
            return query \
                .join(TaskLinkage,
                      and_(Task.task_id == TaskLinkage.task_id,
                           Task.import_source == TaskLinkage.import_source)) \
                .filter(or_(TaskLinkage.resolution == None,
                            TaskLinkage.created_at > recent_tasks_cutoff))

    render_kwargs['tasks_by_domain'] = fetch_tasks_by_domain(db_session, query_limiter)

    todays_date = render_scope_dt.date()
    render_kwargs['compute_render_info_for'] = compute_ignoring_scope(todays_date)

    render_kwargs['to_summary_html'] = to_summary_html

    render_kwargs['to_aio'] = to_aio

    return render_template('tasks-all.html', **render_kwargs)


def _construct_textual_timedelta(
        tasklinkage_dt: datetime,
        reference_dt: datetime,
) -> str | None:
    years_delta = reference_dt.year - tasklinkage_dt.year

    if years_delta >= 2:
        return f"{years_delta} years ago"
    elif years_delta <= -2:
        return f"in {-years_delta} years"

    # if years isn't granular enough, dump it into a months number
    months_delta = reference_dt.month - tasklinkage_dt.month
    months_delta += years_delta * 12

    if months_delta >= 3:
        return f"{months_delta} months ago"
    elif months_delta <= -3:
        return f"in {-months_delta} months"

    # anything left is days
    days_delta = reference_dt - tasklinkage_dt

    if days_delta.days >= 1:
        return f"{days_delta.days} days ago"
    elif days_delta.days <= -1:
        return f"in {-days_delta.days} days"

    # otherwise it's due today; don't print anything because LLM's interpret
    # "today" to mean "this is very important"
    return None


def tasks_as_prompt(
        db_session: Session,
        hide_future: bool = False,
        hide_past: bool = False,
        include_detailed_resolutions: bool = False,
        output_as_json: bool = False,
):
    render_time_dt = datetime.utcnow()
    future_tasks_cutoff = render_time_dt + timedelta(days=91)
    past_tasks_cutoff = render_time_dt - timedelta(days=366)

    additional_filters = [
        TaskLinkage.resolution == None,
    ]
    if hide_past:
        additional_filters.append(TaskLinkage.time_scope > past_tasks_cutoff)
    if hide_future:
        additional_filters.append(TaskLinkage.time_scope < future_tasks_cutoff)

    tasks_by_usefulest_linkage = (
        select(Task.task_id, Task.import_source, func.min(TaskLinkage.time_scope).label('earliest_unresolved_linkage'))
        .where(and_(*additional_filters,
                    TaskLinkage.task_id == Task.task_id,
                    TaskLinkage.import_source == Task.import_source))
        .group_by(Task.task_id, Task.import_source)
        .subquery()
    )

    query = (
        select(Task,
               tasks_by_usefulest_linkage.c.earliest_unresolved_linkage)
        .join(tasks_by_usefulest_linkage,
              and_(Task.task_id == tasks_by_usefulest_linkage.c.task_id,
                   Task.import_source == tasks_by_usefulest_linkage.c.import_source))
        .order_by(func.random())
        .group_by(Task.task_id, Task.import_source)
    )
    task_rows = db_session.execute(query).all()

    final_markdown_descs = []

    task: Task
    usefulest_time_scope: TimeScope
    for (task, usefulest_time_scope) in task_rows:
        output_desc = task.desc
        # Use the override if it exists
        if task.desc_for_llm is not None:
            output_desc = task.desc_for_llm

            # Sometimes the override is an empty string,
            # which indicates we should skip it for LLM output.
            if not task.desc_for_llm.strip():
                continue

        # Filter out link info for any markdown links
        output_desc = re.sub(r'\[(.*?)\]\(.*\)', r'\1', output_desc)

        maybe_category = f", in category \"{task.category}\"" if task.category else ""

        usefulest_ts_dt = datetime(
            year=usefulest_time_scope.year,
            month=usefulest_time_scope.month,
            day=usefulest_time_scope.day,
        )
        fancy_timedelta = _construct_textual_timedelta(usefulest_ts_dt, render_time_dt)
        maybe_overdue = f", due {fancy_timedelta}" if fancy_timedelta else ""

        s = f"- {output_desc}{maybe_category}{maybe_overdue}"
        if "\n" in output_desc:
            maybe_overdue = f"due {fancy_timedelta}, " if fancy_timedelta else ""
            maybe_category = f"in category \"{task.category}\", " if task.category else ""
            # indent the desc text, but need that initial markdown unordered list mark
            indented_output_desc = indent(output_desc, '  ')
            s = f"- {maybe_category}{maybe_overdue}{indented_output_desc[2:]}"

        final_markdown_descs.append(s)

        # And add detail from all sub-linkages, if any:
        if include_detailed_resolutions:
            for tl in task.linkages:
                if tl.detailed_resolution:
                    # Apparently web input gives newlines as `\r\n`, hopefully that's not browser-specific
                    short_res = re.sub(r'<!-- .* -->\r\n', '', tl.detailed_resolution)
                    short_res_lines = short_res.split('\r\n')

                    if short_res_lines and short_res_lines[0]:
                        final_markdown_descs.append("  - " + short_res_lines[0])
                        for line in short_res_lines[1:]:
                            if line.strip():
                                final_markdown_descs.append("    " + line)

    result_text = "\n".join(final_markdown_descs)
    if output_as_json:
        # Format the output specially so it can get parsed directly into llama.cpp
        response = make_response(json.dumps(result_text), 200)
        response.mimetype = "application/json"
        return response

    response = make_response(result_text, 200)
    response.mimetype = "text/plain"
    return response


def edit_tasks_in_scope(
        db_session: Session,
        page_scope: TimeScope,
):
    render_kwargs = {}

    render_kwargs['tasks_by_scope'] = generate_tasks_by_scope(db_session, page_scope)

    render_kwargs['page_title'] = url_for(".do_edit_tasks_in_scope", scope_id=page_scope)

    render_kwargs['to_summary_html'] = to_summary_html

    render_kwargs['to_aio'] = to_aio

    prev_scope = TimeScopeUtils.prev_scope(page_scope)
    render_kwargs['prev_scope'] = \
        f'<a href="{url_for(".do_edit_tasks_in_scope", scope_id=prev_scope)}">{prev_scope}</a>'

    next_scope = TimeScopeUtils.next_scope(page_scope)
    render_kwargs['next_scope'] = \
        f'<a href="{url_for(".do_edit_tasks_in_scope", scope_id=next_scope)}">{next_scope}</a>'

    return render_template('tasks-in-scope.html', **render_kwargs)


def edit_tasks_simple(*args):
    return render_template('tasks-simple.html', tasks_list=args)
