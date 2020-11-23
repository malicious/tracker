from typing import Dict

from flask import Flask
from markupsafe import escape

import notes
import tasks
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
        return tasks.report.report_one_task(escape(task_id))

    @app.route("/report-open-tasks")
    def report_open_tasks():
        return tasks.report.report_open_tasks()

    @app.route("/report-tasks/<scope_str>")
    def report_tasks(scope_str):
        scope = TimeScope(escape(scope_str))
        return tasks.report.report_tasks(scope)

    @app.route("/note/<note_id>")
    def get_note(note_id):
        return notes.report.report_one_note(escape(note_id))

    return app
