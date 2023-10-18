import os
from datetime import datetime

import sqlalchemy
from flask import Flask, Blueprint, abort, redirect, request, url_for
from markupsafe import escape
from sqlalchemy import select
from sqlalchemy.orm import scoped_session, sessionmaker

from tasks_v2.time_scope import TimeScope
# noinspection PyUnresolvedReferences
from . import models, report, update
from .models import Base, Task

db_session = None


def init_app(app: Flask):
    if not app.config['TESTING']:
        load_v2_models(os.path.abspath(os.path.join(app.instance_path, 'tasks-v2.db')))

    _register_endpoints(app)
    _register_rest_endpoints(app)


def load_v2_models(current_db_path: str):
    engine = sqlalchemy.create_engine(
        'sqlite:///' + current_db_path,
        connect_args={
            "check_same_thread": False,
        }
    )

    Base.metadata.create_all(bind=engine)

    # Create a Session object and bind it to the declarative_base
    global db_session
    db_session = scoped_session(sessionmaker(autocommit=False,
                                             autoflush=False,
                                             bind=engine))

    Base.query = db_session.query_property()


def _register_endpoints(app: Flask):
    tasks_v2_bp = Blueprint('tasks-v2', __name__)

    @tasks_v2_bp.route("/tasks")
    def edit_tasks():
        show_resolved = request.args.get('show_resolved')
        hide_future = request.args.get('hide_future')
        return report.edit_tasks_all(show_resolved=show_resolved, hide_future=hide_future)

    @tasks_v2_bp.route("/tasks.in-scope/<scope_id>")
    def do_edit_tasks_in_scope(scope_id):
        if scope_id == 'week':
            this_week = datetime.now().strftime("%G-ww%V")
            return redirect(url_for('.do_edit_tasks_in_scope', scope_id=this_week))
        elif scope_id == 'day':
            this_day = datetime.now().strftime("%G-ww%V.%u")
            return redirect(url_for('.do_edit_tasks_in_scope', scope_id=this_day))

        # Try to read the `scope_id` as an actual TimeScope, so we can fail early.
        scope = TimeScope(scope_id)
        scope.get_type()

        return report.edit_tasks_in_scope(page_scope=scope)

    def _do_edit_one_task(task_id: int):
        task = db_session.execute(
            select(Task)
            .where(Task.task_id == task_id)
        ).scalar_one_or_none()
        if not task:
            abort(404)

        # DEBUG: pass in several tasks, so we can pretend we're a list
        return report.edit_tasks_simple(task, task, task)

    @tasks_v2_bp.route("/tasks/<task_id>")
    def do_edit_one_task(task_id):
        '''
        Temporary endpoint; ultimately, we want this endpoint to be for individual tasks

        For now though, also accept scope_id's and redirect appropriately.
        '''
        try:
            parsed_scope = TimeScope(task_id)
            parsed_scope.get_type()
            return redirect(
                location=url_for('.do_edit_tasks_in_scope', scope_id=parsed_scope),
                code=301,
            )
        except ValueError:
            pass

        return _do_edit_one_task(task_id)

    @tasks_v2_bp.route("/task/<int:task_id>")
    def do_edit_one_task_legacy(task_id):
        return redirect(
            location=url_for('.do_edit_one_task', scope_or_id=task_id),
            code=301,
        )

    app.register_blueprint(tasks_v2_bp)


def _register_rest_endpoints(app: Flask):
    tasks_v2_rest_bp = Blueprint('tasks-v2-rest', __name__)

    @tasks_v2_rest_bp.route("/tasks", methods=['post'])
    def create_task():
        t = update.create_task(db_session, request.form)
        # TODO: do something more creative than redirect back to referrer
        # TODO: This isn't exactly how the anchors (CSS ID's) are generated, pass the scope in or something
        return redirect(f"{request.referrer}#task-{t.task_id}-{t.linkages[0].time_scope_id}")

    @tasks_v2_rest_bp.route("/tasks/<int:task_id>")
    def get_task(task_id):
        return report.report_one_task(escape(task_id))

    @tasks_v2_rest_bp.route("/tasks/<int:task_id>/edit", methods=['post'])
    def edit_task(task_id):
        if not request.args and not request.form and not request.is_json:
            # Assume this was a raw/direct browser request
            # TODO: serve a "single note" template
            abort(400)

        if request.is_json:
            print(request.json)  # sometimes request.data, need to check with unicode
            return {
                "date": datetime.now(),
                "ok": "this was an async request with JS enabled, here's your vaunted output",
            }

        update.update_task(db_session, task_id, request.form)
        return redirect(f"{request.referrer}#{request.form['backlink']}")

    @tasks_v2_rest_bp.route("/tasks/<int:task_id>/<linkage_scope>/edit", methods=['post'])
    def edit_linkage(task_id, linkage_scope):
        if not request.args and not request.form and not request.is_json:
            abort(400)

        if request.is_json:
            print(request.json)
            return {
                "date": datetime.now(),
                "ok": f"this was an async request with JS enabled, see {task_id} and {linkage_scope}",
            }

        update.update_task(db_session, task_id, request.form)
        return redirect(f"{request.referrer}#{request.form['backlink']}")

    app.register_blueprint(tasks_v2_rest_bp, url_prefix='/v2')
