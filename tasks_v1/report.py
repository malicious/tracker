import json
import re
from datetime import datetime
from typing import Iterator, Optional

from flask import render_template
from sqlalchemy.orm import Query

from tasks_v1.models import Task, TaskTimeScope
from tasks_v1.time_scope import TimeScope, TimeScopeUtils


def matching_scopes(task_id) -> Iterator:
    task_time_scopes = TaskTimeScope.query \
        .filter(TaskTimeScope.task_id == task_id) \
        .order_by(TaskTimeScope.time_scope_id) \
        .all()
    return [tts.time_scope_id for tts in task_time_scopes]


def latest_scope(task_id, current_scope: TimeScope) -> Optional[TimeScope]:
    scopes = list(matching_scopes(task_id))
    if not current_scope in scopes:
        return None
    if scopes.index(current_scope) >= len(scopes) - 1:
        return None

    return scopes[-1]


def to_details_html(task: Task):
    # keep parameters to a minimum, to avoid hitting slow DB accesses
    as_json = task.as_json(False, False, False)
    if 'time_scopes' in as_json:
        # make linked TimeScopes clickable
        clickable_scopes = []
        for s in as_json['time_scopes']:
            clickable_scopes.append(f'<a href=/report-tasks/{s}>{s}</a>')
        as_json['time_scopes'] = clickable_scopes

    as_text = json.dumps(as_json, indent=4, ensure_ascii=False)
    # make task_ids clickable
    as_text = re.sub(r'"task_id": (\d*),',
                     r'<a href="/task/\1">"task_id": \1</a>,',
                     as_text)
    # make first_scopes clickable
    as_text = re.sub(r'"first_scope": "(.*)",',
                     r'<a href="/report-tasks/\1">"first_scope": "\1"</a>,',
                     as_text)
    return as_text


def _to_summary_html(t: Task, ref_scope: Optional[TimeScope], print_task_id=False) -> str:
    def _link_replacer(mdown: str):
        return re.sub(r'\[(.+?)\]\((.+?)\)',
                      r"""[\1](<a href="\2">\2</a>)""",
                      mdown)

    def _to_time_html(t: Task) -> str:
        if t.time_estimate is not None and t.time_actual is not None:
            return f"`{t.time_estimate}h => {t.time_actual}h`"
        elif t.time_estimate is not None:
            return f"`{t.time_estimate}h`"
        elif t.time_actual is not None:
            return f"`=> {t.time_actual}`"
        else:
            return f"{t.time_estimate} => {t.time_actual}"

    response_html = ""

    if ref_scope:
        short_scope = TimeScope(t.first_scope).shorten(ref_scope)
        if short_scope:
            response_html += f'\n<span class="time-scope">{short_scope}</span>'

    response_html += f'\n<span class="desc">{_link_replacer(t.desc)}</span>'

    if t.time_estimate is not None or t.time_actual is not None:
        response_html += f'\n<span class="task-time">{_to_time_html(t)}</span>'

    if print_task_id:
        response_html += f'\n<span class="task-id"><a href="/task/{t.task_id}">#{t.task_id}</a></span>'

    return response_html


def to_summary_html(t: Task, ref_scope: Optional[TimeScope] = None) -> str:
    resolution = t.resolution
    # Check if there's a "(roll => ww43.2)"-type message to print
    if ref_scope:
        roll_scope = latest_scope(t.task_id, ref_scope)
        if roll_scope:
            resolution = f"roll => {roll_scope}"

    if t.resolution == "info":
        return '<summary class="task-resolved">\n' + \
               _to_summary_html(t, ref_scope) + \
               '</summary>'

    elif resolution:
        return '<summary class="task-resolved">\n' + \
               f'<span class="resolution">({resolution}) </span>' + \
               _to_summary_html(t, ref_scope) + \
               '</summary>'

    else:
        return '<summary class="task">\n' + \
               _to_summary_html(t, ref_scope, print_task_id=True) + \
               '</summary>'


# Print a short/human-readable scope string
def _short_scope(t: Task, ref_scope):
    short_scope_str = TimeScope(t.first_scope).shorten(ref_scope)
    if short_scope_str:
        return short_scope_str

    return None


def report_one_task(s):
    t = Task.query \
        .filter(Task.task_id == s) \
        .one_or_none()

    return t.as_json()


def report_open_tasks(hide_future_tasks: bool):
    query: Query = Task.query \
        .filter(Task.resolution == None) \
        .order_by(Task.category, Task.created_at)

    future_tasks_cutoff = datetime.now()
    ref_scope = TimeScope(future_tasks_cutoff.date().strftime("%G-ww%V.%u"))
    if hide_future_tasks:
        # TODO: This is a very simple filter that barely does what's requested.
        query = query.filter(Task.first_scope < ref_scope)

    return render_template('task.html',
                           short_scope=_short_scope,
                           tasks_by_scope={ref_scope: query.all()},
                           to_details_html=to_details_html,
                           to_summary_html=to_summary_html)


def report_tasks(scope):
    tasks_by_scope = {}

    subscopes = TaskTimeScope.query \
        .filter(TaskTimeScope.time_scope_id.like(scope + "%")) \
        .order_by(TaskTimeScope.time_scope_id) \
        .all()

    sorted_scopes = [
        *TimeScopeUtils.enclosing_scope(scope, recurse=True),
        scope,
        *[s.time_scope_id for s in subscopes]
    ]

    for s in sorted_scopes:
        tasks = Task.query \
            .join(TaskTimeScope, Task.task_id == TaskTimeScope.task_id) \
            .filter(TaskTimeScope.time_scope_id == s) \
            .order_by(TaskTimeScope.time_scope_id, Task.category) \
            .all()
        tasks_by_scope[TimeScope(s)] = tasks

    prev_scope = TimeScopeUtils.prev_scope(scope)
    prev_scope_html = f'<a href="/report-tasks/{prev_scope}">{prev_scope}</a>'
    next_scope = TimeScopeUtils.next_scope(scope)
    next_scope_html = f'<a href="/report-tasks/{next_scope}">{next_scope}</a>'

    def mdown_desc_cleaner(desc: str):
        desc = re.sub(r'\[(.+?)]\((.+?)\)',
                      r"""[\1](<a href="\2">\2</a>)""",
                      desc)
        return desc

    return render_template('task.html',
                           prev_scope=prev_scope_html,
                           next_scope=next_scope_html,
                           tasks_by_scope=tasks_by_scope,
                           link_replacer=mdown_desc_cleaner,
                           short_scope=_short_scope,
                           to_details_html=to_details_html,
                           to_summary_html=to_summary_html)
