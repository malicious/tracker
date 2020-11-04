import click
from flask.cli import with_appcontext

import notes
import tasks
from tracker.db import content_db


@click.command('import-tasks')
@click.argument('csv_file', type=click.File('r'))
@with_appcontext
def tasks_from_csv(csv_file):
    tasks.add.import_from_csv(csv_file, content_db.session)


@click.command('add-task')
@with_appcontext
def add_task():
    try:
        while True:
            tasks.add.add_from_cli(content_db.session)
            print()
            print("=== starting next task ===")
    except KeyboardInterrupt:
        pass


@click.command('update-task')
@click.argument('task_id', type=click.INT)
@with_appcontext
def update_task(task_id: int):
    tasks.add.update_from_cli(content_db.session, task_id)


@click.command('import-notes')
@click.argument('csv_file', type=click.File('r'))
@with_appcontext
def notes_from_csv(csv_file):
    notes.content.import_from_csv(csv_file, content_db.session)


@click.command('add-summary')
@with_appcontext
def add_summary():
    notes.content.add_from_cli(content_db.session)


def init_app(app):
    app.cli.add_command(tasks_from_csv)
    app.cli.add_command(add_task)
    app.cli.add_command(update_task)
    app.cli.add_command(notes_from_csv)
    app.cli.add_command(add_summary)
