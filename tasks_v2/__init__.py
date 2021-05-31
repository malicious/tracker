from datetime import datetime
import os

import click
import sqlalchemy
from flask import Flask, Blueprint, abort, redirect, request
from flask.cli import with_appcontext
from markupsafe import escape
from sqlalchemy.orm import scoped_session, sessionmaker

# noinspection PyUnresolvedReferences
from . import migrate, models, report
from .models import Base, Task
from tasks_v1.time_scope import TimeScope

db_session = None


def init_app(app: Flask):
    load_v2_models(os.path.abspath(os.path.join(app.instance_path, 'tasks-v2.db')))
    _register_endpoints(app)
    _register_rest_endpoints(app)

    @click.command('tasks_v2-migrate')
    @click.argument('start_index', type=click.INT, required=False)
    @with_appcontext
    def tasks_v2_migrate(start_index):
        from tasks_v1 import db_session as tasks_v1_session
        migrate.migrate_tasks(tasks_v1_session, db_session, start_index)

    app.cli.add_command(tasks_v2_migrate)


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

    @tasks_v2_bp.route("/browse")
    def report_tasks():
        pass

    app.register_blueprint(tasks_v2_bp)


def _register_rest_endpoints(app: Flask):
    tasks_v2_rest_bp = Blueprint('tasks-v2-rest', __name__)

    @tasks_v2_rest_bp.route("/task")
    def create_task():
        pass

    @tasks_v2_rest_bp.route("/task/<int:task_id>")
    def get_task(task_id):
        return report.report_one_task(escape(task_id))

    @tasks_v2_rest_bp.route("/task/<int:task_id>/edit", methods=['get', 'post'])
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

        report.update_task(db_session, task_id, request.form)
        return redirect(request.referrer)

    @tasks_v2_rest_bp.route("/tasks")
    def get_tasks():
        page_scope = None
        try:
            parsed_scope = TimeScope(escape(request.args.get('scope')))
            parsed_scope.get_type()
            page_scope = parsed_scope
        except ValueError:
            pass

        return report.report_tasks(page_scope=page_scope)

    app.register_blueprint(tasks_v2_rest_bp, url_prefix='/v2')
