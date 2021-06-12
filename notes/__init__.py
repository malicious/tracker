import click
from flask import Blueprint, Flask, request
from flask.cli import with_appcontext
from markupsafe import escape

from notes.models import Note
from tasks_v1.time_scope import TimeScope
from tracker.db import content_db
# noinspection PyUnresolvedReferences
from . import add, models, report


def init_app(app: Flask):
    _register_cli(app)
    _register_bp(app)


def _register_cli(app):
    @click.command('import-notes')
    @click.argument('csv_file', type=click.File('r'))
    @with_appcontext
    def notes_from_csv(csv_file):
        add.import_from_csv(csv_file, content_db.session)

    app.cli.add_command(notes_from_csv)


def _register_bp(app):
    notes_bp = Blueprint('notes', __name__)

    @notes_bp.route("/note/<note_id>")
    def get_note(note_id):
        note: Note = Note.query \
            .filter(Note.note_id == note_id) \
            .one()

        return note.to_json(include_domains=True)

    @notes_bp.route("/report-notes")
    def report_notes_all():
        page_scope = None
        try:
            parsed_scope = TimeScope(escape(request.args.get('scope')))
            parsed_scope.get_type()
            page_scope = parsed_scope
        except ValueError:
            pass

        page_domain = request.args.get('domain')

        return report.report_notes(page_scope=page_scope, page_domain=page_domain)

    app.register_blueprint(notes_bp, url_prefix='/')
