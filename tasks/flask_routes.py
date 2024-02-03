from datetime import datetime

from flask import Flask, Blueprint, request, redirect, url_for, abort
from markupsafe import escape
from sqlalchemy import select

from tasks import report, TimeScope, Task, update
from tasks.database import db_session


def _register_endpoints(app: Flask):
    tasks_v2_bp = Blueprint('tasks-v2', __name__)

    @tasks_v2_bp.route("/tasks")
    def edit_tasks():
        show_resolved = request.args.get('show_resolved')
        hide_future = request.args.get('hide_future')
        return report.edit_tasks_all(db_session, show_resolved=show_resolved, hide_future=hide_future)

    @tasks_v2_bp.route("/tasks.as-prompt")
    def do_tasks_as_prompt():
        return report.tasks_as_prompt(db_session)

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

        return report.edit_tasks_in_scope(db_session, page_scope=scope)

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
        # Pick a random category for the purposes of making a link.
        # TODO: Make this code less brittle by sharing it with the stuff in tasks/report.py,
        #       and also wherever that Django-derived sanitization code is.
        domains = ['']
        if t.category is not None and t.category.strip():
            domains = [d.strip() for d in t.category.strip().split('&')]

        domain_css_id = '-'.join(domains[0].split())
        task_backlink = f"task-{t.task_id}-{domain_css_id}"
        return redirect(f"{request.referrer}#{task_backlink}")

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
