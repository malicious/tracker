import re
from datetime import datetime, timedelta
from typing import Optional

from flask import render_template, url_for
from sqlalchemy import or_

from tasks_v1.time_scope import TimeScope, TimeScopeUtils
from tasks_v2.models import Task, TaskLinkage


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
        return '<summary class="task-resolved">\n' + \
               f'<span class="resolution">({tl_exact.resolution}) </span>' + \
               response_html + '\n' + \
               '</summary>'

    # Otherwise, do our best to guess at additional info
    short_scope_str = t.linkages[0].time_scope_id.strftime("%G-ww%V.%u")
    if short_scope_str[0:5] == ref_scope[0:5]:
        short_scope_str = short_scope_str[5:]

    return '<summary class="task">' + \
           f'<span class="time-scope">{short_scope_str}</span>' + \
           response_html + '\n' + \
           '</summary>'


def report_one_task(task_id, return_bare_dict=False):
    task: Task = Task.query \
        .filter(Task.task_id == task_id) \
        .one_or_none()
    if not task:
        return {"error": f"invalid task_id: {task_id}"}

    if return_bare_dict:
        return task.as_json_dict()

    return f'<html><body><pre>{task.as_json()}</pre></body></html>'


def generate_tasks_by_scope(scope_id: str):
    # day-like scope (`%G-ww%V.%u`)
    m = re.fullmatch(r"(\d\d\d\d)-ww([0-5]\d).(\d)", scope_id)
    if m:
        scope = datetime.strptime(scope_id, "%G-ww%V.%u").date()
        tasks = Task.query \
            .join(TaskLinkage, Task.task_id == TaskLinkage.task_id) \
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
                .join(TaskLinkage, Task.task_id == TaskLinkage.task_id) \
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
            quarter_end_date = datetime(start_year+1, 1, 1)
        else:
            quarter_end_date = datetime(start_year, start_month+3, 1)

        tasks_by_scope = {}

        current_day_start = quarter_start_date
        while current_day_start < quarter_end_date:
            tasks = Task.query \
                .join(TaskLinkage, Task.task_id == TaskLinkage.task_id) \
                .filter(TaskLinkage.time_scope == current_day_start.date()) \
                .order_by(TaskLinkage.time_scope, Task.category) \
                .all()

            tasks_by_scope[current_day_start.strftime("%G-ww%V.%u")] = tasks
            current_day_start = current_day_start + timedelta(days=1)

        return tasks_by_scope

    # otherwise, no idea
    raise ValueError(f"No idea how to handle {repr(scope_id)}")


def render_scope(task_date, section_date):
    section_date_str = section_date.strftime("%G-ww%V.%u")

    days_old = (section_date - task_date).days
    color_intensity = 1 / 100.0 * min(100, max(days_old, 0))

    if days_old < 0:
        # Just do normal styling
        color_intensity = 0
    elif days_old == 0:
        # For the same day, we don't care what the day was
        return ''
    elif days_old > 0 and days_old < 370:
        # For this middle ground, do things normally
        pass
    elif days_old > 370:
        # For something over a year old, drop the intensity back to zero
        color_intensity = 0

    # If the year is the same, render as "ww06.5"
    short_date_str = task_date.strftime("%G-ww%V.%u")
    if short_date_str[0:5] == section_date_str[0:5]:
        short_date_str = short_date_str[5:]

    # And the styling
    color_rgb = (200 +  25 * color_intensity,
                 200 - 100 * color_intensity,
                 200 - 100 * color_intensity)
    return f'''
<span class="task-scope" style="color: rgb({color_rgb[0]}, {color_rgb[1]}, {color_rgb[2]})">
  {short_date_str}
</span>'''


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
# TODO: use a consistent "now" datetime, weird things might happen if a day change happens
#
def edit_tasks_all(show_resolved: bool, hide_future: bool):
    render_kwargs = {}

    if show_resolved:
        today_scope_id = datetime.now().strftime("%G-ww%V.%u")
        render_kwargs['tasks_by_scope'] = {
            today_scope_id: Task.query \
                .order_by(Task.category) \
                .all(),
        }
    elif hide_future:
        today_scope_id = datetime.now().strftime("%G-ww%V.%u")
        recent_tasks_cutoff = datetime.utcnow() - timedelta(hours=12)
        future_tasks_cutoff = datetime.utcnow() + timedelta(days=94)

        tasks_query = Task.query \
            .join(TaskLinkage, Task.task_id == TaskLinkage.task_id) \
            .filter(or_(TaskLinkage.resolution == None, \
                        TaskLinkage.created_at > recent_tasks_cutoff)) \
            .filter(TaskLinkage.time_scope < future_tasks_cutoff) \
            .order_by(Task.category, TaskLinkage.time_scope.desc())

        render_kwargs['tasks_by_scope'] = {
            today_scope_id: tasks_query.all(),
        }
    else:
        today_scope_id = datetime.now().strftime("%G-ww%V.%u")
        recent_tasks_cutoff = datetime.utcnow() - timedelta(hours=12)
        tasks_query = Task.query \
            .join(TaskLinkage, Task.task_id == TaskLinkage.task_id) \
            .filter(or_(TaskLinkage.resolution == None, \
                        TaskLinkage.created_at > recent_tasks_cutoff)) \
            .order_by(Task.category)

        render_kwargs['tasks_by_scope'] = {
            today_scope_id: tasks_query.all(),
        }

    todays_date = datetime.now().date()
    render_kwargs['compute_render_info_for'] = compute_ignoring_scope(todays_date)

    render_kwargs['to_summary_html'] = to_summary_html

    return render_template('tasks-all.html', **render_kwargs)


def edit_tasks_in_scope(page_scope: TimeScope):
    render_kwargs = {}

    render_kwargs['tasks_by_scope'] = generate_tasks_by_scope(page_scope)
    # TODO: Replace with something that properly checks the endpoint here
    render_kwargs['page_title'] = f'/tasks/{page_scope}'

    render_kwargs['to_summary_html'] = to_summary_html

    prev_scope = TimeScopeUtils.prev_scope(page_scope)
    render_kwargs['prev_scope'] = f'<a href="{url_for(".edit_tasks_in_scope", scope_id=prev_scope)}">{prev_scope}</a>'

    next_scope = TimeScopeUtils.next_scope(page_scope)
    render_kwargs['next_scope'] = f'<a href="{url_for(".edit_tasks_in_scope", scope_id=next_scope)}">{next_scope}</a>'

    return render_template('tasks-in-scope.html', **render_kwargs)


def edit_tasks_simple(*args):
    return render_template('tasks-simple.html', tasks_list=args)
