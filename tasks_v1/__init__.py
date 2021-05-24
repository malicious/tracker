import click
from flask import Flask, Blueprint, request
from flask.cli import with_appcontext
from markupsafe import escape

from tracker.db import content_db
from .time_scope import TimeScope
# noinspection PyUnresolvedReferences
from . import add, models, report, time_scope


def init_app(app: Flask, legacy_mode=False):
    if legacy_mode:
        _try_migrate(overwrite_temp_db=False)
        _register_endpoints(app)
        _register_cli(app)
    else:
        _try_migrate(overwrite_temp_db=True)
        _register_endpoints(app)


def _try_migrate(overwrite_temp_db: bool):
    pass


def _register_endpoints(app: Flask):
    tasks_v1_bp = Blueprint('tasks-v1', __name__)

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
    @click.command('import-tasks')
    @click.argument('csv_file', type=click.File('r'))
    @with_appcontext
    def tasks_from_csv(csv_file):
        add.import_from_csv(csv_file, content_db.session)

    @click.command('task-add-one')
    @with_appcontext
    def task_add_one():
        add.add_from_cli(content_db.session)

    @click.command('task-add-multiple')
    @with_appcontext
    def task_add_multiple():
        try:
            while True:
                add.add_from_cli(content_db.session)
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
            add.update(content_db.session, scopes, category, resolution, task_id)

    @click.command('task-update-interactive')
    @click.argument('task_ids', type=click.INT, nargs=-1)
    @with_appcontext
    def task_update_interactive(task_ids):
        try:
            for task_id in task_ids:
                print(f"=== task_id: {task_id} ===")

                add.update_from_cli(content_db.session, task_id)
                print()

        except KeyboardInterrupt:
            pass

    app.cli.add_command(tasks_from_csv)
    app.cli.add_command(task_add_one)
    app.cli.add_command(task_add_multiple)
    app.cli.add_command(task_update_batch)
    app.cli.add_command(task_update_interactive)
