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


@click.command('task-add-one')
@with_appcontext
def task_add_one():
    tasks.add.add_from_cli(content_db.session)


@click.command('task-add-multiple')
@with_appcontext
def task_add_multiple():
    try:
        while True:
            tasks.add.add_from_cli(content_db.session)
            print()
            print("=== starting next task ===")
    except KeyboardInterrupt:
        pass


@click.command('task-update-batch')
@click.option('--add-scope', 'scopes', multiple=True)
@click.option('--category')
@click.option('--resolution', 'resolution')
@click.argument('task_ids', type=click.INT, nargs=-1)
@with_appcontext
def task_update_batch(scopes, category, resolution, task_ids):
    for task_id in task_ids:
        tasks.add.update(content_db.session, scopes, category, resolution, task_id)


@click.command('task-update-interactive')
@click.argument('task_ids', type=click.INT, nargs=-1)
@with_appcontext
def task_update_interactive(task_ids):
    try:
        for task_id in task_ids:
            print(f"=== task_id: {task_id} ===")

            tasks.add.update_from_cli(content_db.session, task_id)
            print()

    except KeyboardInterrupt:
        pass


@click.command('import-notes')
@click.argument('csv_file', type=click.File('r'))
@with_appcontext
def notes_from_csv(csv_file):
    notes.add.import_from_csv(csv_file, content_db.session)


def init_app(app):
    app.cli.add_command(tasks_from_csv)
    app.cli.add_command(task_add_one)
    app.cli.add_command(task_add_multiple)
    app.cli.add_command(task_update_batch)
    app.cli.add_command(task_update_interactive)
    app.cli.add_command(notes_from_csv)
