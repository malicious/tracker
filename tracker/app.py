from typing import Dict

from flask import Flask
from markupsafe import escape

import tasks
from notes.content import note_to_json, report_notes_by_domain
from tasks.content import task_and_scopes_to_json
from tasks.time_scope import TimeScope
from . import cli, db


def create_app(settings_overrides: Dict = {}):
    app = Flask(__name__, instance_relative_config=True)
    db.init_app(app, settings_overrides)
    cli.init_app(app)

    @app.route("/time_scope/<scope_str>")
    def get_time_scope(scope_str: str):
        return TimeScope(escape(scope_str)).to_json_dict()

    @app.route("/task/<task_id>")
    def get_task(task_id):
        return task_and_scopes_to_json(escape(task_id))

    @app.route("/report-open-tasks")
    def report_open_tasks():
        return tasks.content.report_open_tasks()

    @app.route("/report-tasks/<scope_str>")
    def report_tasks(scope_str):
        scope = TimeScope(escape(scope_str))
        return tasks.content.report_tasks(scope)

    @app.route("/note/<note_id>")
    def get_note(note_id):
        return note_to_json(escape(note_id))

    @app.route("/report-notes/<domain>")
    def report_notes(domain):
        by_domain = report_notes_by_domain(escape(domain), content_db.session)
        if by_domain:
            return by_domain

        return {"error": f"invalid search: {repr(domain)}"}

    return app
