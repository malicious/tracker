import os

import click
import sqlalchemy
from flask import Blueprint, Flask, request
from flask.cli import with_appcontext
from markupsafe import escape
from sqlalchemy.orm import scoped_session, sessionmaker

from notes.models import Note, Base
from tasks_v1.time_scope import TimeScope
# noinspection PyUnresolvedReferences
from . import add, models, report

db_session = None


def init_app(app: Flask):
    load_models(os.path.abspath(os.path.join(app.instance_path, 'notes.db')))
    _register_cli(app)
    _register_bp(app)


def _register_cli(app):
    @click.command('import-notes')
    @click.argument('csv_file', type=click.File('r'))
    @with_appcontext
    def notes_from_csv(csv_file):
        add.import_from_csv(csv_file, db_session)

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


def load_models(current_db_path: str):
    engine = sqlalchemy.create_engine('sqlite:///' + current_db_path)

    Base.metadata.create_all(bind=engine)

    # Create a Session object and bind it to the declarative_base
    global db_session
    db_session = scoped_session(sessionmaker(autocommit=False,
                                             autoflush=False,
                                             bind=engine))

    Base.query = db_session.query_property()
