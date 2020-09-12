import csv
import io
import json
import re

from flask import render_template
from sqlalchemy.exc import StatementError

from tasks.models import Task, TaskTimeScope
from tasks.time_scope import TimeScope, TimeScopeUtils


def import_from_csv(csv_file, session):
    id_remapper = {}

    for csv_entry in csv.DictReader(csv_file):
        # Sort out TimeScopes first
        if not csv_entry['scopes']:
            raise ValueError(f"No scopes specified for Task: \n{json.dumps(csv_entry, indent=4)}")

        sorted_scopes = sorted([TimeScope(scope_str) for scope_str in csv_entry['scopes'].split() if not None])
        if not sorted_scopes:
            print(json.dumps(csv_entry, indent=4))
            raise ValueError(f"No valid scopes for Task: \n{json.dumps(csv_entry, indent=4)}")
        csv_entry['first_scope'] = sorted_scopes[0]

        # If there's a parent_id, run it through the remapper first
        if 'parent_id' in csv_entry and csv_entry['parent_id']:
            csv_entry['parent_id'] = id_remapper[csv_entry['parent_id']]

        # Check for a pre-existing Task before creating one
        new_task = Task.from_csv(csv_entry)
        task = Task.query \
            .filter_by(desc=new_task.desc, created_at=new_task.created_at) \
            .one_or_none()
        if not task:
            session.add(new_task)
            task = new_task
            try:
                session.commit()
            except StatementError as e:
                print("Hit exception when parsing:")
                print(json.dumps(csv_entry, indent=4))
                session.rollback()
                continue

        # Add the task_id to the remapper
        if 'id' in csv_entry and csv_entry['id']:
            id_remapper[csv_entry['id']] = task.task_id

        # Then create the linkages
        for scope in sorted_scopes:
            new_tts = TaskTimeScope(task_id=task.task_id, time_scope_id=scope)
            tts = session.query(TaskTimeScope) \
                .filter_by(task_id=task.task_id, time_scope_id=scope) \
                .one_or_none()
            if not tts:
                session.add(new_tts)
                tts = new_tts

        session.commit()


def populate_test_data(s):
    # manual task insertion
    s.add(Task(desc="test task row 1", first_scope="2042-ww06.9"))
    s.add(Task(desc="test task row 2", first_scope="2042-ww06.9"))
    s.add(Task(desc="test task row 3", first_scope="2042-ww06.9"))
    s.add(Task(desc="test task row 4", first_scope="2042-ww06.9", category="row 4 category"))
    s.commit()

    # faux-CSV insertion
    test_csv_data = """desc,category,time_estimate,scopes
task 5,,0.8,2042-ww06.9
task 6,"cat with space",,2042-ww06.9 2025-ww02.4
task 7,,,2042-ww06.9 2002-ww02.2 2002-ww02.2
task 7,,,2042-ww06.9 2002-ww02.2
"""
    import_from_csv(io.StringIO(test_csv_data), s)


def report_tasks(scope):
    tasks_by_scope = {}

    superscopes = TimeScopeUtils.enclosing_scopes(scope)
    subscopes = TaskTimeScope.query \
        .filter(TaskTimeScope.time_scope_id.like(scope + "%")) \
        .order_by(TaskTimeScope.time_scope_id) \
        .all()

    sorted_scopes = [s for s in superscopes] + [scope] + [s.time_scope_id for s in subscopes]
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

    return render_template('base.html',
                           prev_scope=prev_scope_html,
                           next_scope=next_scope_html,
                           tasks_by_scope=tasks_by_scope,
                           link_replacer=mdown_desc_cleaner)
