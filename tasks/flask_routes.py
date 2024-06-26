from datetime import datetime

from flask import Flask, Blueprint, request, redirect, url_for, abort
from markupsafe import escape
from sqlalchemy import select

from util import TimeScope
from . import report, update
from .database import get_db
from .database_models import Task


def _register_endpoints(app: Flask):
    tasks_v2_bp = Blueprint('tasks-v2', __name__)

    @tasks_v2_bp.route("/tasks")
    def edit_tasks():
        return report.edit_tasks_all(
            get_db(),
            show_resolved=request.args.get('show_resolved'),
            hide_future=request.args.get('hide_future'),
            ignore_categories=request.args.get('ignore_categories'),
        )

    @tasks_v2_bp.route("/tasks.as-prompt")
    def do_tasks_as_prompt():
        return report.tasks_as_prompt(
            get_db(),
            hide_future=request.args.get('hide_future'),
            hide_past=request.args.get('hide_past'),
            include_detailed_resolutions=request.args.get('include_detailed_resolutions'),
        )

    @tasks_v2_bp.route("/tasks.in-scope/<scope_id>")
    def do_edit_tasks_in_scope(scope_id):
        if scope_id == 'week':
            this_week = datetime.now().strftime("%G-ww%V")
            return redirect(url_for('.do_edit_tasks_in_scope', scope_id=this_week))
        elif scope_id == 'day':
            this_day = datetime.now().strftime("%G-ww%V.%u")
            return redirect(url_for('.do_edit_tasks_in_scope', scope_id=this_day))

        scope = TimeScope(scope_id)
        scope.validate()

        return report.edit_tasks_in_scope(get_db(), page_scope=scope)

    def _do_edit_matching_tasks(task_id: int):
        tasks = get_db().execute(
            select(Task)
            .where(Task.task_id == task_id)
        ).scalars()
        if not tasks:
            abort(404)

        # DEBUG: pass in several tasks, so we can pretend we're a list
        return report.edit_tasks_simple(*tasks)

    @tasks_v2_bp.route("/tasks/<task_id>")
    def do_edit_matching_task_ids(task_id):
        '''
        Temporary endpoint; ultimately, we want this endpoint to be for individual tasks

        For now though, also accept scope_id's and redirect appropriately.
        '''
        try:
            parsed_scope = TimeScope(task_id)
            parsed_scope.validate()
            return redirect(
                location=url_for('.do_edit_tasks_in_scope', scope_id=parsed_scope),
                code=301,
            )
        except ValueError:
            pass

        return _do_edit_matching_tasks(task_id)

    @tasks_v2_bp.route("/task/<int:task_id>")
    def do_edit_one_task_legacy(task_id):
        return redirect(
            location=url_for('.do_edit_matching_task_ids', scope_or_id=task_id),
            code=301,
        )

    app.register_blueprint(tasks_v2_bp)


def _register_rest_endpoints(app: Flask):
    tasks_v2_rest_bp = Blueprint('tasks-v2-rest', __name__)

    @tasks_v2_rest_bp.route("/tasks", methods=['post'])
    def create_task():
        t = update.create_task(get_db(), request.form)
        # Pick a random category for the purposes of making a link.
        domain_for_link = next(t.split_categories(), '')

        domain_for_link_as_css_id = '-'.join(domain_for_link.split())
        task_backlink = f"task-{t.task_id}-{domain_for_link_as_css_id}"
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
                "ok"  : "this was an async request with JS enabled, here's your vaunted output",
            }

        update.update_task(get_db(), task_id, request.form)
        return redirect(f"{request.referrer}#{request.form['backlink']}")

    @tasks_v2_rest_bp.route("/tasks/<int:task_id>/<linkage_scope>/edit", methods=['post'])
    def edit_linkage(task_id, linkage_scope):
        if not request.args and not request.form and not request.is_json:
            abort(400)

        if request.is_json:
            print(request.json)
            return {
                "date": datetime.now(),
                "ok"  : f"this was an async request with JS enabled, see {task_id} and {linkage_scope}",
            }

        update.update_task(get_db(), task_id, request.form)
        return redirect(f"{request.referrer}#{request.form['backlink']}")

    app.register_blueprint(tasks_v2_rest_bp, url_prefix='/v2')
