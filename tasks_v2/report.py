import json
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

    return '<summary class="task">' + \
           response_html + '\n' + \
           '</summary>'


def report_one_task(task_id):
    task: Task = Task.query \
        .filter(Task.task_id == task_id) \
        .one_or_none()
    if not task:
        return {"error": f"invalid task_id: {task_id}"}

    return task.to_json_dict()


def generate_tasks_by_scope(page_scope: Optional[TimeScope]):
    # Identify the scopes that we care about
    page_scopes_all = []

    if page_scope is not None:
        page_scope_linkages = TaskLinkage.query \
            .filter(TaskLinkage.time_scope_id.like(page_scope + "%")) \
            .order_by(TaskLinkage.time_scope_id) \
            .all()
        page_scopes_all = [
            *TimeScopeUtils.enclosing_scope(page_scope, recurse=True),
            page_scope,
            *[tl.time_scope_id for tl in page_scope_linkages],
        ]
    else:
        page_scope_linkages = TaskLinkage.query \
            .order_by(TaskLinkage.time_scope_id) \
            .all()
        page_scopes_all = [
            tl.time_scope_id for tl in page_scope_linkages
        ]

    # Identify all tasks within those scopes
    tasks_by_scope = {}

    for scope in page_scopes_all:
        tasks = Task.query \
            .join(TaskLinkage, Task.task_id == TaskLinkage.task_id) \
            .filter(TaskLinkage.time_scope_id == scope) \
            .order_by(TaskLinkage.time_scope_id, Task.category) \
            .all()
        tasks_by_scope[TimeScope(scope)] = tasks

    return tasks_by_scope


def report_tasks(page_scope: Optional[TimeScope]):
    render_kwargs = {}

    # Identify all tasks within those scopes
    render_kwargs['tasks_by_scope'] = generate_tasks_by_scope(page_scope)

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
