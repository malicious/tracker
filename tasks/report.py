import json
import re
from datetime import datetime
from typing import Iterator, Dict

from flask import render_template
from sqlalchemy.orm import Query

from tasks.models import Task, TaskTimeScope
from tasks.time_scope import TimeScope, TimeScopeUtils


def list_scopes(task_id) -> Iterator:
    task_time_scopes = TaskTimeScope.query \
        .filter(TaskTimeScope.task_id == task_id) \
        .all()
    return [tts.time_scope_id for tts in task_time_scopes]


def task_and_scopes_to_json(task_id) -> Dict:
    def get_parentiest_task(task: Task) -> Dict:
        # Look for the highest-level parent
        while task.parent_id:
            task = Task.query \
                .filter(Task.task_id == task.parent_id) \
                .one()

        return task.to_json(True)

    task = Task.query \
        .filter(Task.task_id == task_id) \
        .one()

    return {
        "task": get_parentiest_task(task),
        "time_scopes": list_scopes(task_id),
    }


def _pretty_print_task(task: Task):
    as_json = task_and_scopes_to_json(task.task_id)
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
    # make first_scope_id clickable
    as_text = re.sub(r'"first_scope": "(.*)",',
                     r'<a href="/report-tasks/\1">"first_scope": "\1"</a>,',
                     as_text)
    return as_text


def report_open_tasks():
    query: Query = Task.query \
        .filter(Task.resolution == None) \
        .order_by(Task.category, Task.created_at)

    def link_replacer(mdown: str):
        return re.sub(r'\[(.+?)\]\((.+?)\)',
                      r"""[\1](<a href="\2">\2</a>)""",
                      mdown)

    time_scope_shortener = lambda task, ref: TimeScope(task.first_scope).shorten(ref)

    ref_scope = TimeScope(datetime.now().date().strftime("%G-ww%V.%u"))
    return render_template('task.html',
                           tasks_by_scope={ref_scope: query.all()},
                           link_replacer=link_replacer,
                           pretty_print_task=_pretty_print_task,
                           time_scope_shortener=time_scope_shortener)


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
                           pretty_print_task=_pretty_print_task,
                           time_scope_shortener=time_scope_shortener)
