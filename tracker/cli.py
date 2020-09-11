import click
from flask.cli import with_appcontext

import tasks
from tasks.content import import_from_csv
from tracker.content import content_db


@click.command('reset-db')
@with_appcontext
def reset_db():
    content_db.drop_all()
    content_db.create_all()


@click.command('migrate-db')
@with_appcontext
def migrate_db():
    content_db.create_all()


@click.command('test-db')
@with_appcontext
def populate_test_db():
    tasks.content.populate_test_data(content_db.session)


@click.command('import-tasks')
@click.argument('csv_file', type=click.File('r'))
@with_appcontext
def tasks_from_csv(csv_file):
    import_from_csv(csv_file, content_db.session)
