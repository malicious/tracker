import os
import shutil
import sqlite3
from typing import Callable

import click
import sqlalchemy
from flask import Flask, Blueprint, request
from flask.cli import with_appcontext
from markupsafe import escape
from sqlalchemy.orm import scoped_session, sessionmaker

# noinspection PyUnresolvedReferences
from . import add, models, report, time_scope
from .models import Base
from .time_scope import TimeScope

LEGACY_DB_NAME = 'tasks.db'
CURRENT_DB_NAME = 'tasks-v1.db'

db_session = None


def init_app(app: Flask, legacy_mode=False, readonly_mode=True):
    """
    Maybe-init the Tasks_v1 schemas

    - legacy mode allows read/write
    - read-only allows endpoint access
    - with both set to False, database + v1 schema aren't loaded at all
    """

    def _generate_instance_path(name: str) -> str:
        return os.path.abspath(os.path.join(app.instance_path, name))

    if legacy_mode:
        if not app.config['TESTING']:
            _try_migrate(_generate_instance_path, preserve_target_db=True)
            load_v1_models(_generate_instance_path(CURRENT_DB_NAME))

        _register_endpoints(app)
        _register_cli(app)
    elif readonly_mode:
        if not app.config['TESTING']:
            _try_migrate(_generate_instance_path, preserve_target_db=True)
            load_v1_models(_generate_instance_path(CURRENT_DB_NAME))

        _register_endpoints(app)
    else:
        pass


def _try_migrate(generate_path: Callable[[str], str], preserve_target_db: bool):
    """
    Prep to migrate content from tasks_v1 to tasks_v2.

    - Moves database from tasks.db => tasks-v1.db, if needed.
    - Also renames the SQL tables, appending a "-v1" suffix.

    A within-database migration might be easier, but there's no use cases at the moment.
    """
    current_db_path = generate_path(CURRENT_DB_NAME)
    legacy_db_path = generate_path(LEGACY_DB_NAME)

    if preserve_target_db and os.path.exists(current_db_path):
        print(f"WARN: found database file at \"{current_db_path}\", ignoring legacy {LEGACY_DB_NAME}")
        return

    if not os.path.exists(legacy_db_path):
        print(f"INFO: no legacy database file, can't migrate from {legacy_db_path}")
        return

    # Copy to a temporary file, while we alter the table
    temp_current_db_path = current_db_path + '-tmp'
    shutil.copy2(legacy_db_path, temp_current_db_path)

    # Alter the table
    connection = sqlite3.connect(temp_current_db_path)
    cur = connection.cursor()
    try:
        cur.execute('ALTER TABLE Tasks RENAME TO "Tasks-v1"')
        cur.execute('ALTER TABLE TaskTimeScopes RENAME TO "TaskTimeScopes-v1"')
    finally:
        cur.close()

    # Put it in its final position as `tasks-v1.db`
    shutil.move(temp_current_db_path, current_db_path)
    print(f"INFO: done migrating legacy database file to {current_db_path}")


def load_v1_models(current_db_path: str):
    engine = sqlalchemy.create_engine('sqlite:///' + current_db_path)

    Base.metadata.create_all(bind=engine)

    # Create a Session object and bind it to the declarative_base
    global db_session
    db_session = scoped_session(sessionmaker(autocommit=False,
                                             autoflush=False,
                                             bind=engine))

    Base.query = db_session.query_property()


def _register_endpoints(app: Flask):
    tasks_v1_bp = Blueprint('tasks-v1', __name__)

    @tasks_v1_bp.route("/time_scope/<scope_str>")
    def get_time_scope(scope_str: str):
        return TimeScope(escape(scope_str)).to_json_dict()

    @tasks_v1_bp.route("/task/<task_id>")
    def get_task(task_id):
        return report.report_one_task(escape(task_id))

    @tasks_v1_bp.route("/report-open-tasks")
    def report_open_tasks():
        hide_future_tasks = False

        parsed_hide_future_tasks = escape(request.args.get('hide_future_tasks'))
        # TODO: should use `inputs.boolean` from flask-restful
        if parsed_hide_future_tasks == 'true':
            hide_future_tasks = True

        return report.report_open_tasks(hide_future_tasks=hide_future_tasks)

    @tasks_v1_bp.route("/report-tasks/<scope_str>")
    def report_tasks(scope_str):
        scope = TimeScope(escape(scope_str))
        return report.report_tasks(scope)

    app.register_blueprint(tasks_v1_bp, url_prefix='/')


def _register_cli(app: Flask):
    @click.command('import-tasks', help='[legacy] Import tasks from CSV file')
    @click.argument('csv_file', type=click.File('r'))
    @with_appcontext
    def tasks_from_csv(csv_file):
        add.import_from_csv(csv_file, db_session)

    @click.command('task-add-one', help='[legacy] Add one task via interactive CLI')
    @with_appcontext
    def task_add_one():
        add.add_from_cli(db_session)

    @click.command('task-add-multiple', help='[legacy] Add multiple tasks')
    @with_appcontext
    def task_add_multiple():
        try:
            while True:
                add.add_from_cli(db_session)
                print()
                print("=== starting next task ===")
        except KeyboardInterrupt:
            pass

    @click.command('task-update-batch', help='[legacy] Batch update existing tasks')
    @click.option('--add-scope', 'scopes', multiple=True)
    @click.option('--category')
    @click.option('--resolution', 'resolution')
    @click.argument('task_ids', type=click.INT, nargs=-1)
    @with_appcontext
    def task_update_batch(scopes, category, resolution, task_ids):
        for task_id in task_ids:
            add.update(db_session, scopes, category, resolution, task_id)

    @click.command('task-update-interactive', help='[legacy] Update specified tasks via interactive CLI')
    @click.argument('task_ids', type=click.INT, nargs=-1)
    @with_appcontext
    def task_update_interactive(task_ids):
        try:
            for task_id in task_ids:
                print(f"=== task_id: {task_id} ===")

                add.update_from_cli(db_session, task_id)
                print()

        except KeyboardInterrupt:
            pass

    app.cli.add_command(tasks_from_csv)
    app.cli.add_command(task_add_one)
    app.cli.add_command(task_add_multiple)
    app.cli.add_command(task_update_batch)
    app.cli.add_command(task_update_interactive)
