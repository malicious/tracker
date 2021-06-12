from flask import Blueprint, Flask, request
from markupsafe import escape

from notes.models import Note
from tasks_v1.time_scope import TimeScope
# noinspection PyUnresolvedReferences
from . import add, models, report


def init_app(app: Flask):
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
