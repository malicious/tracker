import os

import click
from flask import Blueprint, request
from flask.cli import with_appcontext
from flask.json import JSONEncoder
from markupsafe import escape
import sqlalchemy
from sqlalchemy.orm import scoped_session, sessionmaker

from notes_v2 import add, report
from notes_v2.models import Base, Note
from notes_v2.report import clear_html_cache
# noinspection PyUnresolvedReferences
from . import models

db_session = None


def init_app(app):
    clear_html_cache()

    if not app.config['TESTING']:
        load_models(os.path.abspath(os.path.join(app.instance_path, 'notes-v2.db')))
    _register_endpoints(app)
    _register_rest_endpoints(app)

    @click.command('n2/add', help='Import notes from a CSV file')
    @click.argument('csv_file', type=click.File('r'))
    @with_appcontext
    def n2_add(csv_file):
        add.all_from_csv(db_session, csv_file, expect_duplicates=False)

    app.cli.add_command(n2_add)

    @click.command('n2/update', help='Update notes from a partially-imported CSV file')
    @click.argument('csv_file', type=click.File('r'))
    @with_appcontext
    def n2_update(csv_file):
        add.all_from_csv(db_session, csv_file, expect_duplicates=True)
        print("WARN: Jinja caching still in effect, please restart the flask server to apply changes")

    app.cli.add_command(n2_update)

    @click.command('n2/export', help='Export all notes as CSV output')
    @click.option('--write-note-id/--skip-note-id', default=False, show_default=True)
    @with_appcontext
    def n2_export(write_note_id):
        add.all_to_csv(write_note_id=write_note_id)
        print("WARN: Jinja caching still in effect, please restart the flask server to apply changes")

    app.cli.add_command(n2_export)


def load_models(current_db_path: str):
    engine = sqlalchemy.create_engine('sqlite:///' + current_db_path)

    Base.metadata.create_all(bind=engine)

    # Create a Session object and bind it to the declarative_base
    global db_session
    db_session = scoped_session(sessionmaker(autocommit=False,
                                             autoflush=False,
                                             bind=engine))

    Base.query = db_session.query_property()


def _register_endpoints(app):
    notes_v2_bp = Blueprint('notes-v2', __name__)

    @notes_v2_bp.route("/note_v2/<int:note_id>")
    def edit_one_note(note_id):
        n = Note.query.filter_by(note_id=note_id).one()
        return report.edit_notes_simple(n, n)

    @notes_v2_bp.route("/notes")
    def edit_notes():
        page_scopes = [escape(arg) for arg in request.args.getlist('scope')]
        page_domains = [escape(arg) for arg in request.args.getlist('domain')]
        return report.edit_notes(page_domains, page_scopes)

    app.register_blueprint(notes_v2_bp, url_prefix='')


def _register_rest_endpoints(app):
    notes_v2_rest_bp = Blueprint('notes-v2-rest', __name__)

    # Add JSON encoder to handle Note types
    class NoteEncoder(JSONEncoder):
        def default(self, obj):
            if isinstance(obj, Note):
                return obj.as_json(include_domains=True)
            return super(NoteEncoder, self).default(obj)

    notes_v2_rest_bp.json_encoder = NoteEncoder

    @notes_v2_rest_bp.route("/note/<int:note_id>")
    def get_note(note_id):
        n = Note.query.filter_by(note_id=escape(note_id)).one()
        return n.as_json(True)

    @notes_v2_rest_bp.route("/notes")
    def get_notes():
        page_scopes = [escape(arg) for arg in request.args.getlist('scope')]
        page_domains = [escape(arg) for arg in request.args.getlist('domain')]
        return report.notes_json_tree(page_domains, page_scopes)

    @notes_v2_rest_bp.route("/stats/domains")
    def get_domain_stats():
        return report.domain_stats(db_session)

    app.register_blueprint(notes_v2_rest_bp, url_prefix='/v2')
