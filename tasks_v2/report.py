import json
from datetime import datetime
from typing import Optional

from flask import render_template

from tasks.time_scope import TimeScope, TimeScopeUtils
from tasks_v2.models import Task, TaskLinkage


def to_details_html(t: Task):
    as_text = json.dumps(t.to_json_dict(), indent=4, ensure_ascii=False)
    return as_text


def to_summary_html(t: Task, ref_scope: Optional[TimeScope] = None) -> str:
    response_html = ""
    response_html += f'\n<span class="desc">{t.desc}</span>'
    response_html += f'\n<span class="task-id"><a href="/task-v2/{t.task_id}">#{t.task_id}</a></span>'

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
    short_scope_str = TimeScope(t.linkages[0].time_scope_id).shorten(ref_scope)
    return '<summary class="task">' + \
            f'<span class="time-scope">{short_scope_str}</span>' + \
            response_html + '\n' + \
            '</summary>'


def report_one_task(task_id):
    task: Task = Task.query \
        .filter(Task.task_id == task_id) \
        .one_or_none()
    if not task:
        return {"error": f"invalid task_id: {task_id}"}

    as_text = json.dumps(task.to_json_dict(), indent=4, ensure_ascii=False)
    return f'<html><body><pre>{as_text}</pre></body></html>'


def generate_tasks_by_scope(page_scope: TimeScope):
    # Identify the scopes that we care about
    linkages_query = TaskLinkage.query \
        .filter(TaskLinkage.time_scope_id.like(page_scope + "%")) \
        .order_by(TaskLinkage.time_scope_id)

    page_scopes_all = [
        *TimeScopeUtils.enclosing_scope(page_scope, recurse=True),
        page_scope,
        *[tl.time_scope_id for tl in linkages_query.all()],
    ]

    # Identify all tasks within those scopes
    tasks_by_scope = {}

    for scope in page_scopes_all:
        tasks_in_scope_query = Task.query \
            .join(TaskLinkage, Task.task_id == TaskLinkage.task_id) \
            .filter(TaskLinkage.time_scope_id == scope) \
            .order_by(TaskLinkage.time_scope_id, Task.category)

        tasks_by_scope[TimeScope(scope)] = tasks_in_scope_query.all()

    return tasks_by_scope


def generate_open_tasks():
    tasks_query = Task.query \
        .join(TaskLinkage, Task.task_id == TaskLinkage.task_id) \
        .filter(TaskLinkage.resolution == None) \
        .order_by(Task.category, TaskLinkage.time_scope_id)

    ref_scope = TimeScope(datetime.now().date().strftime("%G-ww%V.%u"))
    return {ref_scope: tasks_query.all()}


def report_tasks(page_scope: Optional[TimeScope]):
    render_kwargs = {}

    # Identify all tasks within those scopes
    if page_scope:
        render_kwargs['tasks_by_scope'] = generate_tasks_by_scope(page_scope)
    else:
        render_kwargs['tasks_by_scope'] = generate_open_tasks()

    # If there are previous/next links, add them
    if page_scope:
        prev_scope = TimeScopeUtils.prev_scope(page_scope)
        render_kwargs['prev_scope'] = f'<a href="/report-tasks-v2?scope={prev_scope}">{prev_scope}</a>'
        next_scope = TimeScopeUtils.next_scope(page_scope)
        render_kwargs['next_scope'] = f'<a href="/report-tasks-v2?scope={next_scope}">{next_scope}</a>'

    # Tell template about how to format Tasks
    render_kwargs['to_details_html'] = to_details_html
    render_kwargs['to_summary_html'] = to_summary_html

    return render_template('task.html', **render_kwargs)
