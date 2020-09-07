import csv
import io
from typing import Dict

import click
from dateutil import parser
from flask.cli import with_appcontext

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
        for field in ["category", "resolution", "parent_id", "time_estimate", "time_actual"]:
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
        }

        # Skip null fields, per Google JSON style guide:
        # https://google.github.io/styleguide/jsoncstyleguide.xml#Empty/Null_Property_Values
        for field in ["category", "created_at", "resolution", "parent_id", "time_estimate", "time_actual"]:
            if getattr(self, field):
                response_dict[field] = getattr(self, field)

        return response_dict


# ------------------
# Task import/export
# ------------------

def _import_from_csv(csv_file, session):
    for csv_entry in csv.DictReader(csv_file):
        new_task = Task.from_csv(csv_entry)
        existing_task = session.query(Task).filter_by(desc=new_task.desc, created_at=new_task.created_at)
        if not existing_task.first():
            session.add(new_task)

    session.commit()


@click.command('import-tasks')
@click.argument('csv_file', type=click.File('r'))
@with_appcontext
def tasks_from_csv(csv_file):
    _import_from_csv(csv_file, db.session)


@click.command('test-db')
@with_appcontext
def populate_test_data():
    s = db.session

    # manual task insertion
    s.add(Task(desc="test task row 1"))
    s.add(Task(desc="test task row 2"))
    s.add(Task(desc="test task row 3"))
    s.add(Task(desc="test task row 4", category="row 4 category"))
    s.commit()

    # faux-CSV insertion
    test_csv_data = """desc,category,time_estimate,
task 5,,0.8,
task 6,"cat with space",,
task 7,,,
task 7,,,
"""
    _import_from_csv(io.StringIO(test_csv_data), s)
