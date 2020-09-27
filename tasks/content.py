import csv
import io
import json
import re
from datetime import datetime
from typing import Dict, Iterator

from flask import render_template
from sqlalchemy.exc import StatementError

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


def add_from_cli(session):
    # Read relevant scopes
    today_scope = TimeScope(datetime.now().strftime("%G-ww%V.%u"))
    requested_scopes = input(f"Enter scopes [{today_scope}]: ")
    if not requested_scopes:
        requested_scopes = today_scope

    requested_scopes = sorted([TimeScope(s) for s in requested_scopes.split()])
    try:
        [s.get_type() for s in requested_scopes]
    except ValueError as e:
        print(e)
        return
    print(f"parsed as {requested_scopes}")
    print("")

    # Read description for the task
    desc = input(f"Enter description: ")

    t = Task(desc=desc, first_scope=requested_scopes[0], created_at=datetime.now())
    try:
        session.add(t)
        session.commit()
    except StatementError as e:
        print("")
        print("Hit exception when parsing:")
        print(json.dumps(t.to_json(), indent=4))
        session.rollback()
        return

    # Add scopes etc
    for scope in requested_scopes:
        tts = TaskTimeScope(task_id=t.task_id, time_scope_id=scope)
        session.add(tts)
    session.commit()

    # Done, print output
    print(f"Created task {t.task_id}")


def update_from_cli(session, task_id):
    # Open relevant task
    t = Task.query \
        .filter(Task.task_id == task_id) \
        .one()

    # Print matching scopes
    scopes = [tts.time_scope_id for tts in \
              TaskTimeScope.query \
                  .filter(TaskTimeScope.task_id == task_id) \
                  .all()]
    print(f"Existing scopes: {scopes}")

    # Decide what we're adding
    today_scope = TimeScope(datetime.now().strftime("%G-ww%V.%u"))
    requested_scope = input(f"Enter scope to add [{today_scope}]: ")
    if requested_scope:
        try:
            TimeScope(requested_scope).get_type()
        except ValueError as e:
            print(e)
            return
    else:
        requested_scope = today_scope

    # Decide whether we're resolving it
    if t.resolution:
        print(f"Task already has a resolution: {t.resolution}")
        requested_resolution = input(f"Enter resolution to set [{t.resolution}]: ")
        if requested_resolution:
            t.resolution = requested_resolution
            session.add(t)
    else:
        requested_resolution = input(f"Enter resolution to set: ")
        t.resolution = requested_resolution
        session.add(t)

    # And update the scopes, maybe
    if TimeScope(requested_scope) not in scopes:
        session.add(TaskTimeScope(task_id=t.task_id, time_scope_id=requested_scope))

    session.commit()
    print(f"Updated task {t.task_id}")
    print(json.dumps(t.to_json(), indent=4))


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

    def pretty_print_task(task: Task):
        as_json = task_and_scopes_to_json(task.task_id)
        # make linked TimeScopes clickable
        clickable_scopes = []
        for s in as_json['time_scopes']:
            clickable_scopes.append(f'<a href=/report-tasks/{s}>{s}</a>')
        as_json['time_scopes'] = clickable_scopes

        as_text = json.dumps(as_json, indent=4)
        # make task_ids clickable
        as_text = re.sub(r'"task_id": (\d*),',
                         r'<a href="/task/\1">"task_id": \1</a>,',
                         as_text)
        # make first_scope_id clickable
        as_text = re.sub(r'"first_scope": "(.*)",',
                         r'<a href="/report-tasks/\1">"first_scope": "\1"</a>,',
                         as_text)
        return as_text

    return render_template('task.html',
                           prev_scope=prev_scope_html,
                           next_scope=next_scope_html,
                           tasks_by_scope=tasks_by_scope,
                           link_replacer=mdown_desc_cleaner,
                           pretty_print_task=pretty_print_task,
                           time_scope_shortener=time_scope_shortener)
