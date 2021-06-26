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


def render_scope(task_date, section_date_str: str):
    section_date = datetime.strptime(section_date_str, "%G-ww%V.%u").date()

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


def get_resolution(t: Task):
    # If there's any open linkages, return unresolved
    # TODO: import the db session and use exists()/scalar()
    open_linkages_exist = TaskLinkage.query \
        .filter_by(task_id=t.task_id, resolution=None) \
        .all()
    if open_linkages_exist:
        return None

    final_linkage = TaskLinkage.query \
        .filter_by(task_id=t.task_id) \
        .order_by(TaskLinkage.time_scope) \
        .all()[-1]
    return final_linkage.resolution


def has_resolution(t: Task, ref_scope):
    ref_linkage = t.linkage_at(ref_scope, create_if_none=False)
    if ref_linkage and ref_linkage.resolution:
        return ref_linkage

    return get_resolution(t)


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

    # Print a short/human-readable scope string
    def short_scope(t: Task, ref_scope):
        short_scope_str = t.linkages[0].time_scope_id
        if short_scope_str[0:5] == ref_scope[0:5]:
            short_scope_str = short_scope_str[5:]

        return short_scope_str

    render_kwargs['short_scope'] = short_scope
    render_kwargs['has_resolution'] = has_resolution
    render_kwargs['get_resolution'] = get_resolution
    render_kwargs['render_scope'] = render_scope

    render_kwargs['to_summary_html'] = to_summary_html

    return render_template('tasks.html', **render_kwargs)


def edit_tasks_simple(*args):
    return render_template('tasks-simple.html', tasks_list=args)
