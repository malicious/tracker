import click
from flask.cli import with_appcontext

import tasks
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
    tasks.content.import_from_csv(csv_file, content_db.session)


@click.command('add-task')
@with_appcontext
def add_task():
    tasks.content.add_from_cli(content_db.session)


def init_app(app):
    app.cli.add_command(reset_db)
    app.cli.add_command(migrate_db)
    app.cli.add_command(populate_test_db)
    app.cli.add_command(tasks_from_csv)
    app.cli.add_command(add_task)
