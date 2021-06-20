from datetime import datetime
import os

import click
import sqlalchemy
from flask import Flask, Blueprint, abort, redirect, request, url_for
from flask.cli import with_appcontext
from markupsafe import escape
from sqlalchemy.orm import scoped_session, sessionmaker

# noinspection PyUnresolvedReferences
from . import migrate, models, report, update
from .models import Base, Task
from tasks_v1 import db_session as tasks_v1_session
from tasks_v1.models import Task as Task_v1
from tasks_v1.time_scope import TimeScope

db_session = None


def init_app(app: Flask):
    if not app.config['TESTING']:
        load_v2_models(os.path.abspath(os.path.join(app.instance_path, 'tasks-v2.db')))
    _register_endpoints(app)
    _register_rest_endpoints(app)

    @click.command('t2-migrate-one', help='Migrate one legacy task to new format')
    @click.argument('task_id', type=click.INT)
    @with_appcontext
    def t2_migrate_one(task_id):
        t1 = Task_v1.query \
            .filter_by(task_id=task_id) \
            .one()

        migrate.do_one(db_session, t1)

    app.cli.add_command(t2_migrate_one)

    @click.command('t2-migrate-all', help='Migrate all legacy tasks')
    @click.option('--delete', type=click.BOOL)
    @with_appcontext
    def t2_migrate_all(delete):
        migrate.do_multiple(tasks_v1_session, db_session, delete)

    app.cli.add_command(t2_migrate_all)


def load_v2_models(current_db_path: str):
    engine = sqlalchemy.create_engine('sqlite:///' + current_db_path)

    Base.metadata.create_all(bind=engine)

    # Create a Session object and bind it to the declarative_base
    global db_session
    if db_session:
        print("WARN: db_session already exists, creating a new one anyway")
        db_session = None

    db_session = scoped_session(sessionmaker(autocommit=False,
                                             autoflush=False,
                                             bind=engine))

    Base.query = db_session.query_property()


def _register_endpoints(app: Flask):
    tasks_v2_bp = Blueprint('tasks-v2', __name__)

    @tasks_v2_bp.route("/tasks")
    def report_tasks():
        show_resolved = request.args.get('show_resolved')
        return report.report_tasks(show_resolved=show_resolved)

    @tasks_v2_bp.route("/tasks/<scope_id>")
    def report_tasks_in_scope(scope_id):
        page_scope = None
        try:
            parsed_scope = TimeScope(scope_id)
            parsed_scope.get_type()
            page_scope = parsed_scope
        except ValueError:
            pass

        return report.report_tasks(page_scope=page_scope)

    @tasks_v2_bp.route("/task/<int:task_id>")
    def report_one_task(task_id):
        return report.report_one_task(escape(task_id))

    app.register_blueprint(tasks_v2_bp)


def _register_rest_endpoints(app: Flask):
    tasks_v2_rest_bp = Blueprint('tasks-v2-rest', __name__)

    @tasks_v2_rest_bp.route("/task", methods=['post'])
    def create_task():
        task = update.create_task(db_session, request.form)
        return redirect(url_for(".get_task", task_id=task.task_id))

    @tasks_v2_rest_bp.route("/task/<int:task_id>")
    def get_task(task_id):
        return report.report_one_task(escape(task_id))

    @tasks_v2_rest_bp.route("/task/<int:task_id>/edit", methods=['post'])
    def edit_task(task_id):
        if not request.args and not request.form and not request.json:
            # Assume this was a raw/direct browser request
            # TODO: serve a "single note" template
            abort(400)

        if request.json:
            print(request.json) # sometimes request.data, need to check with unicode
            return {
                "date": datetime.now(),
                "ok": "this was an async request with JS enabled, here's your vaunted output",
            }

        update.update_task(db_session, task_id, request.form)
        return redirect(f"{request.referrer}#{request.form['backlink']}")

    @tasks_v2_rest_bp.route("/task/<int:task_id>/<linkage_scope>/edit", methods=['post'])
    def edit_linkage(task_id, linkage_scope):
        if not request.args and not request.form and not request.json:
            abort(400)

        if request.json:
            print(request.json)
            return {
                "date": datetime.now(),
                "ok": f"this was an async request with JS enabled, see {task_id} and {linkage_scope}",
            }

        update.update_task(db_session, task_id, request.form)
        return redirect(f"{request.referrer}#{request.form['backlink']}")

    @tasks_v2_rest_bp.route("/tasks", methods=['get'])
    def get_tasks():
        return {
            "date": datetime.now(),
            "ok": "not implemented",
        }

    app.register_blueprint(tasks_v2_rest_bp, url_prefix='/v2')
