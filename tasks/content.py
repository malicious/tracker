import csv
import io
import json

from sqlalchemy.exc import StatementError

from tasks.models import Task, TaskTimeScope
from tasks.time_scope import TimeScope


def import_from_csv(csv_file, session):
    for csv_entry in csv.DictReader(csv_file):
        # Sort out TimeScopes first
        if not csv_entry['scopes']:
            raise ValueError(f"No scopes specified for Task: \n{json.dumps(csv_entry, indent=4)}")

        sorted_scopes = sorted([TimeScope(scope_str) for scope_str in csv_entry['scopes'].split() if not None])
        if not sorted_scopes:
            print(json.dumps(csv_entry, indent=4))
            raise ValueError(f"No valid scopes for Task: \n{json.dumps(csv_entry, indent=4)}")
        csv_entry['first_scope'] = sorted_scopes[0]

        # Check for a pre-existing Task before creating one
        new_task = Task.from_csv(csv_entry)
        task = session.query(Task) \
            .filter_by(desc=new_task.desc, created_at=new_task.created_at) \
            .first()
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

        # Then create the linkages
        for scope in sorted_scopes:
            new_tts = TaskTimeScope(task_id=task.task_id, time_scope_id=scope)
            tts = session.query(TaskTimeScope) \
                .filter_by(task_id=task.task_id, time_scope_id=scope) \
                .first()
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
