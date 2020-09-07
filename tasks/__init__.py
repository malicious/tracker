import csv
import io
from typing import Dict

import click
from flask.cli import with_appcontext

from tracker.content import content_db


def _import_from_csv(csv_file, session):
    for csv_entry in csv.DictReader(csv_file):
        session.add(Task.from_csv(csv_entry))

    session.commit()


@click.command('import-tasks')
@click.argument('csv_file', type=click.File('r'))
@with_appcontext
def tasks_from_csv(csv_file):
    _import_from_csv(csv_file, content_db.session)


@click.command('test-db')
@with_appcontext
def populate_test_data():
    s = content_db.session

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
"""
    _import_from_csv(io.StringIO(test_csv_data), s)


class Task(content_db.Model):
    __tablename__ = 'Tasks'
    task_id = content_db.Column(content_db.Integer, primary_key=True, nullable=False, unique=True)
    desc = content_db.Column(content_db.String, nullable=False)
    category = content_db.Column(content_db.String)
    created_at = content_db.Column(content_db.DateTime)
    resolution = content_db.Column(content_db.String)
    parent_id = content_db.Column(content_db.Integer, content_db.ForeignKey('Tasks.task_id'))
    time_estimate = content_db.Column(content_db.Float)
    time_actual = content_db.Column(content_db.Float)
    __table_args__ = (
        content_db.UniqueConstraint('desc', 'created_at'),
    )

    @staticmethod
    def from_csv(csv_entry):
        t = Task(desc=csv_entry['desc'])
        for field in ["category", "created_at", "resolution", "parent_id", "time_estimate", "time_actual"]:
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
