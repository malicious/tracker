import json
import re
from datetime import datetime
from typing import Iterator, Dict, Optional

from flask import render_template
from sqlalchemy.orm import Query

from tasks.models import Task, TaskTimeScope
from tasks.time_scope import TimeScope, TimeScopeUtils


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


def _to_json(task: Task,
             include_scopes: bool,
             include_children: bool) -> Dict:
    response_dict = task.to_json_dict()

    if include_children:
        child_json = [
            _to_json(child, include_scopes, include_children)
            for child in task.get_children()
        ]
        if child_json:
            response_dict['children'] = child_json

    if include_scopes:
        scopes = matching_scopes(task.task_id)
        if scopes:
            response_dict['time_scopes'] = scopes

    return response_dict


def to_json(task: Task,
            include_scopes: bool = True,
            include_parents: bool = True,
            include_children: bool = False):
    def get_parentiest_task(task: Task) -> Dict:
        "Look for the highest-level parent"
        while task.parent_id:
            task = task.get_parent()
        return task

    if include_parents:
        parentiest_task = get_parentiest_task(task)

        # Override value of include_children, because we have no way of limiting depth
        include_children = True

    else:
        parentiest_task = Task.query.filter(Task.task_id == task.task_id).one()

    return _to_json(parentiest_task, include_scopes, include_children)


def to_details_html(task: Task):
    # keep parameters to a minimum, to avoid hitting slow DB accesses
    as_json = to_json(task, False, False, False)
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

def _to_summary_html(t: Task, ref_scope: Optional[TimeScope]) -> str:
    def _link_replacer(mdown: str):
        return re.sub(r'\[(.+?)\]\((.+?)\)',
                      r"""[\1](<a href="\2">\2</a>)""",
                      mdown)

    def _to_time_html(t: Task) -> str:
        if t.time_estimate and t.time_actual:
            return f"`{t.time_estimate}h => {t.time_actual}h`"
        elif t.time_estimate:
            return f"`{t.time_estimate}h`"
        elif t.time_actual:
            return f"`=> {t.time_actual}`"
        else:
            return ""

    response_html = ""

    if ref_scope:
        short_scope = TimeScope(t.first_scope).shorten(ref_scope)
        if short_scope:
            response_html += f'\n<span class="time-scope">{short_scope}</span>'

    response_html += f'\n<span class="desc">{_link_replacer(t.desc)}</span>'

    if t.time_estimate or t.time_actual:
        response_html += f'\n<span class="task-time">{_to_time_html(t)}</span>'

    return response_html


def to_summary_html(t: Task, ref_scope: Optional[TimeScope] = None) -> str:
    if t.resolution == "info":
        return '<summary class="task-resolved">\n' + \
               _to_summary_html(t, ref_scope) + \
               '</summary>'

    elif t.resolution:
        return '<summary class="task-resolved">\n' + \
               f'<span class="resolution">({t.resolution}) </span>' + \
               _to_summary_html(t, ref_scope) + \
               '</summary>'

    else:
        # Check if there's a "(roll => ww43.2)"-type message to print
        if ref_scope:
            roll_scope = latest_scope(t.task_id, ref_scope)
            if roll_scope:
                return '<summary class="task-resolved">\n' + \
                       f'<span class="resolution">(roll => {roll_scope}) </span>' + \
                       _to_summary_html(t, ref_scope) + \
                       '</summary>'

        return '<summary class="task">\n' + \
               _to_summary_html(t, ref_scope) + \
               '</summary>'


def report_one_task(s):
    t = Task.query \
        .filter(Task.task_id == s) \
        .one_or_none()

    return to_json(t)


def report_open_tasks():
    query: Query = Task.query \
        .filter(Task.resolution == None) \
        .order_by(Task.category, Task.created_at)

    time_scope_shortener = lambda task, ref: TimeScope(task.first_scope).shorten(ref)

    ref_scope = TimeScope(datetime.now().date().strftime("%G-ww%V.%u"))
    return render_template('task.html',
                           tasks_by_scope={ref_scope: query.all()},
                           time_scope_shortener=time_scope_shortener,
                           to_details_html=to_details_html,
                           to_summary_html=to_summary_html)


def report_tasks(scope):
    tasks_by_scope = {}

    subscopes = TaskTimeScope.query \
        .filter(TaskTimeScope.time_scope_id.like(scope + "%")) \
        .order_by(TaskTimeScope.time_scope_id) \
        .all()

    sorted_scopes = [] \
                    + TimeScopeUtils.enclosing_scope(scope, TimeScope.Type.quarter) \
                    + TimeScopeUtils.enclosing_scope(scope, TimeScope.Type.week) \
                    + [scope] \
                    + [s.time_scope_id for s in subscopes]

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

    time_scope_shortener = lambda task, ref: TimeScope(task.first_scope).shorten(ref)

    return render_template('task.html',
                           prev_scope=prev_scope_html,
                           next_scope=next_scope_html,
                           tasks_by_scope=tasks_by_scope,
                           link_replacer=mdown_desc_cleaner,
                           time_scope_shortener=time_scope_shortener,
                           to_details_html=to_details_html,
                           to_summary_html=to_summary_html)
