from typing import Dict

from flask import Flask, request
from markupsafe import escape

import notes
import tasks_v1
from tasks_v1.time_scope import TimeScope
from . import cli, db


def create_app(settings_overrides: Dict = {}):
    app = Flask(__name__, instance_relative_config=True)
    db.init_app(app, settings_overrides)
    tasks_v1.init_app(app)
    cli.init_app(app)

    try:
        from flask_debugtoolbar import DebugToolbarExtension

        app.config['SECRET_KEY'] = '7'
        toolbar = DebugToolbarExtension(app)
    except ImportError:
        pass

    @app.route("/time_scope/<scope_str>")
    def get_time_scope(scope_str: str):
        return TimeScope(escape(scope_str)).to_json_dict()

    @app.route("/note/<note_id>")
    def get_note(note_id):
        return notes.report.report_one_note(escape(note_id))

    @app.route("/report-notes")
    def report_notes_all():
        page_scope = None
        try:
            parsed_scope = TimeScope(escape(request.args.get('scope')))
            parsed_scope.get_type()
            page_scope = parsed_scope
        except ValueError:
            pass

        page_domain = request.args.get('domain')

        return notes.report.report_notes(page_scope=page_scope, page_domain=page_domain)

    return app
