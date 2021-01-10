import csv
import json
import re
from datetime import datetime
from typing import List

from dateutil import parser
from sqlalchemy.exc import OperationalError, StatementError

import tasks
from tasks.models import Task, TaskTimeScope
from tasks.time_scope import TimeScope


def from_csv(csv_entry) -> Task:
    t = Task(desc=csv_entry['desc'])
    if 'created_at' in csv_entry and csv_entry['created_at']:
        t.created_at = parser.parse(csv_entry['created_at'])
    for field in ["first_scope", "category", "resolution", "parent_id", "time_estimate", "time_actual"]:
        value = csv_entry.get(field)
        setattr(t, field, value if value else None)

    return t


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

            # Next, confirm that our parent depth isn't greater than 5
            def will_hit_max_depth(task_id, depth):
                if depth <= 0:
                    return True

                task = Task.query \
                    .filter(Task.task_id == task_id) \
                    .one_or_none()
                if not task.parent_id:
                    return False

                return will_hit_max_depth(task.parent_id, depth - 1)

            if will_hit_max_depth(csv_entry['parent_id'], 4):
                print(f"Will hit maximum Task depth for parent_id: {csv_entry['parent_id']}")
                print(f"Skipping Task:")
                print(json.dumps(csv_entry, indent=4))
                continue

        # Check for a pre-existing Task before creating one
        new_task = from_csv(csv_entry)
        task: Task = Task.query \
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
        else:
            # Update existing task
            task.resolution = new_task.resolution
            task.category = new_task.category
            task.parent_id = new_task.parent_id

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


class Color:
    RED = '\033[1;31;48m'
    END = '\033[1;37;0m'


def _read_validated_scopes() -> List[str]:
    """
    Prompts the user to enter a list of space-separated TimeScopes

    - if nothing is entered, fall back to the "current" scope
    - if whitespace is entered, return an empty list
    - TimeScopes are checked for validity
    """
    today_scope = TimeScope(datetime.now().strftime("%G-ww%V.%u"))
    entered_scopes = input(f"Enter scopes to add [{today_scope}]: {Color.RED}")
    print(Color.END, end='', flush=True)

    if not entered_scopes:
        requested_scopes = [today_scope]
    elif not entered_scopes.strip():
        requested_scopes = []
    else:
        requested_scopes = [TimeScope(s) for s in entered_scopes.split()]
        try:
            [s.get_type() for s in requested_scopes]
        except ValueError as e:
            print(e)
            return

    return requested_scopes


def add_from_cli(session):
    # Read description for the task
    desc = input(f"Enter description: {Color.RED}")
    print(Color.END, end='', flush=True)

    # Read relevant scopes
    requested_scopes = sorted(_read_validated_scopes())
    if not len(requested_scopes):
        requested_scopes = [TimeScope(datetime.now().strftime("%G-ww%V.%u"))]
        print(f"   => defaulting to {requested_scopes}")
    if len(requested_scopes) > 1:
        print(f"   => parsed as {requested_scopes}")

    # Create a Task, now that we have all required fields
    t = Task(desc=desc,
             first_scope=requested_scopes[0],
             created_at=datetime.now())

    # And a time_estimate
    time_estimate = input(f"Enter time_estimate: {Color.RED}")
    if time_estimate is not None and time_estimate != "":
        if not re.fullmatch(r"\d+\.\d", time_estimate):
            print(Color.END, end='')
            print("time_estimate must be in format like `12.0` (\"\\d+\\.\\d\"), exiting")
            print()
            return
        t.time_estimate = time_estimate
    print(Color.END, end='', flush=True)

    # Try committing the Task
    try:
        session.add(t)
        session.commit()
    except StatementError as e:
        print()
        print("Hit exception when parsing:")
        print(json.dumps(t.to_json_dict(), indent=4))
        session.rollback()
        return

    # Try creating the TaskTimeScopes
    for requested_scope in requested_scopes:
        session.add(TaskTimeScope(task_id=t.task_id, time_scope_id=requested_scope))
    session.commit()

    print()
    print(f"Created task {t.task_id}")
    print(json.dumps(t.to_json_dict(), indent=4))


def update(session, requested_scopes, category, resolution, task_id):
    t: Task = Task.query.filter(Task.task_id == task_id).one()

    if requested_scopes:
        # TODO: This is redundant, should let sqlalchemy enforce the no-dupes
        existing_scopes = tasks.report.matching_scopes(task_id)

        for requested_scope in requested_scopes:
            if TimeScope(requested_scope) not in existing_scopes:
                session.add(TaskTimeScope(task_id=t.task_id, time_scope_id=requested_scope))

    if category:
        t.category = category
        session.add(t)

    if resolution:
        t.resolution = resolution
        session.add(t)

    try:
        session.commit()
        print()
        print(f"Updated task {t.task_id}")
        print(json.dumps(t.to_json_dict(), indent=4))
    except OperationalError as e:
        print()
        print(e)
        return


def update_from_cli(session, task_id):
    # Open relevant task
    t: Task = Task.query.filter(Task.task_id == task_id).one()
    task_name = t.desc[:70] if len(t.desc) > 70 else t.desc
    print(task_name)
    print()

    matching_scopes = tasks.report.matching_scopes(task_id)
    print(f"Existing scopes => {', '.join(matching_scopes)}")

    # Read relevant scopes
    requested_scopes = _read_validated_scopes()

    # Decide whether we're resolving it
    if t.resolution:
        print(f"Task already has a resolution => {t.resolution}")
        requested_resolution = input(f"Enter resolution to set [{t.resolution}]: {Color.RED}")
        print(Color.END, end='', flush=True)
    else:
        requested_resolution = input(f"Enter resolution to set: {Color.RED}")
        print(Color.END, end='', flush=True)

    if requested_resolution:
        t.resolution = requested_resolution
        session.add(t)

    # And update the scopes, maybe
    for requested_scope in requested_scopes:
        if TimeScope(requested_scope) not in matching_scopes:
            session.add(TaskTimeScope(task_id=t.task_id, time_scope_id=requested_scope))

    try:
        session.commit()
        print()
        print(f"Updated task {t.task_id}")
        print(json.dumps(t.to_json_dict(), indent=4))
    except OperationalError as e:
        print()
        print(e)
        return
