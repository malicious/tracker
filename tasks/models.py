import csv
import io
from typing import Dict

import click
from dateutil import parser
from flask.cli import with_appcontext

from tasks.time_scope import TimeScope
from tracker.content import content_db as db


class Task(db.Model):
    __tablename__ = 'Tasks'
    task_id = db.Column(db.Integer, primary_key=True, nullable=False, unique=True)
    desc = db.Column(db.String, nullable=False)
    first_scope = db.Column(db.String(20), nullable=False)
    category = db.Column(db.String)
    created_at = db.Column(db.DateTime)
    resolution = db.Column(db.String)
    parent_id = db.Column(db.Integer, db.ForeignKey('Tasks.task_id'))
    time_estimate = db.Column(db.Float)
    time_actual = db.Column(db.Float)
    __table_args__ = (
        db.UniqueConstraint('desc', 'created_at'),
    )

    @staticmethod
    def from_csv(csv_entry):
        t = Task(desc=csv_entry['desc'])
        if 'created_at' in csv_entry and csv_entry['created_at']:
            t.created_at = parser.parse(csv_entry['created_at'])
        for field in ["first_scope", "category", "resolution", "parent_id", "time_estimate", "time_actual"]:
            value = csv_entry.get(field)
            setattr(t, field, value if value else None)

        return t

    def to_json(self) -> Dict:
        """
        Build a dict for JSON response
        """
        response_dict = {
            'task_id': self.task_id,
            'desc': self.desc,
            'first_scope': self.first_scope,
        }

        # Skip null fields, per Google JSON style guide:
        # https://google.github.io/styleguide/jsoncstyleguide.xml#Empty/Null_Property_Values
        if self.created_at:
            response_dict['created_at'] = str(self.created_at)

        for field in ["category", "resolution", "parent_id", "time_estimate", "time_actual"]:
            if getattr(self, field):
                response_dict[field] = getattr(self, field)

        return response_dict

    def short_scope(self, reference_scope) -> str:
        return TimeScope(self.first_scope).shorten(reference_scope)

    def short_time(self) -> str:
        if self.time_estimate and self.time_actual:
            return f"`{self.time_estimate}h => {self.time_actual}h`"
        elif self.time_estimate:
            return f"`{self.time_estimate}h`"
        elif self.time_actual:
            return f"`=> {self.time_actual}`"
        else:
            return ""


class TaskTimeScope(db.Model):
    __tablename__ = 'TaskTimeScopes'
    task_id = db.Column(db.Integer, db.ForeignKey("Tasks.task_id"), primary_key=True, nullable=False)
    time_scope_id = db.Column(db.String, primary_key=True, nullable=False)
    __table_args__ = (
        db.UniqueConstraint('task_id', 'time_scope_id'),
    )


# ------------------
# Task import/export
# ------------------

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