import csv
import io

import click
from flask.cli import with_appcontext

from tasks.models import Task, TaskTimeScope
from tasks.time_scope import TimeScope
from tracker.content import content_db as db


def import_from_csv(csv_file, session):
    for csv_entry in csv.DictReader(csv_file):
        # Sort out TimeScopes first
        sorted_scopes = sorted([TimeScope(scope_str) for scope_str in csv_entry['scopes'].split() if not None])
        if not sorted_scopes:
            raise ValueError(f"No scopes provided for given Task")
        csv_entry['first_scope'] = sorted_scopes[0]

        # Check for a pre-existing Task before creating one
        new_task = Task.from_csv(csv_entry)
        task = session.query(Task) \
            .filter_by(desc=new_task.desc, created_at=new_task.created_at) \
            .first()
        if not task:
            session.add(new_task)
            task = new_task
            session.commit()

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


@click.command('import-tasks')
@click.argument('csv_file', type=click.File('r'))
@with_appcontext
def tasks_from_csv(csv_file):
    import_from_csv(csv_file, db.session)


@click.command('test-db')
@with_appcontext
def populate_test_data():
    s = db.session

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
