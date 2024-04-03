import operator
import re
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

from flask import render_template, url_for
from sqlalchemy import or_, select, and_
from sqlalchemy.orm import Session

from tasks.database_models import Task, TaskLinkage
from tasks.report.render import to_aio, make_renderer
from util import TimeScope


def to_summary_html(t: Task, ref_scope: TimeScope | None = None) -> str:
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


def report_one_task(task_id, return_bare_dict=False):
    """
    NB This intentionally lists tasks across all `import_source`s, since we don't have an API to filter them

    TODO: Actually this breaks with multiple tasks, because `.one_or_none()`
    """
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
        for d in task.split_categories(default=''):
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


# NB the arguments are kinda weird and inconsistent because they're default-false
#
def edit_tasks_all(
        db_session: Session,
        show_resolved: bool,
        hide_future: bool,
        ignore_categories: bool,
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

    if ignore_categories:
        task_rows = db_session.execute(
            query_limiter(select(Task)
                          .group_by(Task.task_id, Task.import_source))
        ).all()

        def sort_time(t: Task):
            """TODO: This should be doable with an SQLAlchemy-level sort."""
            return (
                max(map(operator.attrgetter('time_scope'), t.linkages)),
                t.task_id,
            )

        tasks = [row[0] for row in task_rows]
        sorted_tasks = sorted(tasks, key=sort_time, reverse=True)

        render_kwargs['tasks_by_domain'] = {'': sorted_tasks}

    else:
        render_kwargs['tasks_by_domain'] = fetch_tasks_by_domain(db_session, query_limiter)

    def is_readonly_import_source(import_source: str):
        if import_source == '':
            return False

        return True

    todays_date = render_scope_dt.date()
    render_kwargs['compute_task_render_info'] = make_renderer(db_session, todays_date, is_readonly_import_source)

    render_kwargs['to_summary_html'] = to_summary_html

    render_kwargs['to_aio'] = to_aio

    return render_template('tasks-all.html', **render_kwargs)


def edit_tasks_in_scope(
        db_session: Session,
        page_scope: TimeScope,
):
    render_kwargs = {}

    render_kwargs['tasks_by_scope'] = generate_tasks_by_scope(db_session, page_scope)

    render_kwargs['page_title'] = url_for(".do_edit_tasks_in_scope", scope_id=page_scope)

    render_kwargs['to_summary_html'] = to_summary_html

    render_kwargs['to_aio'] = to_aio

    prev_scope = page_scope.prev
    render_kwargs['prev_scope'] = \
        f'<a href="{url_for(".do_edit_tasks_in_scope", scope_id=prev_scope)}">{prev_scope}</a>'

    next_scope = page_scope.next
    render_kwargs['next_scope'] = \
        f'<a href="{url_for(".do_edit_tasks_in_scope", scope_id=next_scope)}">{next_scope}</a>'

    return render_template('tasks-in-scope.html', **render_kwargs)


def edit_tasks_simple(*args):
    return render_template('tasks-simple.html', tasks_list=args)
