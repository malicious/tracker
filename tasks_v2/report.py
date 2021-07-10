import re
from datetime import datetime, timedelta
from dateutil import parser
from typing import Optional

from flask import render_template, url_for

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


def compute_render_info_for(page_scope: Optional[TimeScope]):
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

    Returns a function that returns a tuple of (scope to print, resolution to print)
    """
    def compute_with_scope(t, ref_scope_id: TimeScope):
        # If we have an _exact_ match for this scope, return its resolution
        ref_linkage = t.linkage_at(ref_scope_id, create_if_none=False)
        if ref_linkage:
            return '', ref_linkage.resolution

        # Otherwise, why is this Task showing up for this scope?
        raise ValueError(f"Error computing render info, {t} doesn't have anything for {ref_scope_id}")

    def compute_ignoring_scope(t, _: TimeScope):
        # TODO: import the db session and use exists()/scalar()
        open_linkages_exist = TaskLinkage.query \
            .filter_by(task_id=t.task_id, resolution=None) \
            .all()
        # If every linkage is closed, just return the "last" resolution
        if not open_linkages_exist:
            return '', t.linkages[-1].resolution

        # If exactly one open linkage remains, use its source scope
        todays_date = datetime.now().date()
        if len(t.linkages) == 1:
            rendered_scope = render_scope(t.linkages[0].time_scope, todays_date)
            return rendered_scope, t.linkages[-1].resolution

        # By this point multiple linkages exist, but at least one is open
        latest_open = [tl for tl in t.linkages if not tl.resolution][-1]
        if latest_open.time_scope > todays_date:
            return latest_open.time_scope_id, "FUTURE"
        else:
            rendered_scope = render_scope(latest_open.time_scope, todays_date)
            return rendered_scope, t.linkages[-1].resolution

    if page_scope:
        return compute_with_scope
    else:
        return compute_ignoring_scope


def edit_tasks(page_scope: Optional[TimeScope] = None,
               show_resolved: bool = False):
    render_kwargs = {}

    # If there are previous/next links, add them
    if page_scope:
        prev_scope = TimeScopeUtils.prev_scope(page_scope)
        render_kwargs['prev_scope'] = f'<a href="{url_for(".edit_tasks_in_scope", scope_id=prev_scope)}">{prev_scope}</a>'
        next_scope = TimeScopeUtils.next_scope(page_scope)
        render_kwargs['next_scope'] = f'<a href="{url_for(".edit_tasks_in_scope", scope_id=next_scope)}">{next_scope}</a>'

    # Identify all tasks within those scopes
    if page_scope:
        render_kwargs['tasks_by_scope'] = generate_tasks_by_scope(page_scope)
    elif show_resolved:
        today_scope_id = datetime.now().strftime("%G-ww%V.%u")
        render_kwargs['tasks_by_scope'] = {
            today_scope_id: Task.query \
                .order_by(Task.category) \
                .all(),
        }
    else:
        today_scope_id = datetime.now().strftime("%G-ww%V.%u")
        tasks_query = Task.query \
            .join(TaskLinkage, Task.task_id == TaskLinkage.task_id) \
            .filter(TaskLinkage.resolution == None) \
            .order_by(Task.category)

        render_kwargs['tasks_by_scope'] = {
            today_scope_id: tasks_query.all(),
        }

    render_kwargs['compute_render_info_for'] = compute_render_info_for(page_scope)

    render_kwargs['to_summary_html'] = to_summary_html

    return render_template('tasks.html', **render_kwargs)


def edit_tasks_simple(*args):
    return render_template('tasks-simple.html', tasks_list=args)
