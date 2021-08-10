import os

import click
from flask import Blueprint
from flask.cli import with_appcontext
from markupsafe import escape
import sqlalchemy
from sqlalchemy.orm import scoped_session, sessionmaker

from notes_v2 import add, report
from notes_v2.models import Base, Note
# noinspection PyUnresolvedReferences
from . import models

db_session = None


def init_app(app):
    if not app.config['TESTING']:
        load_models(os.path.abspath(os.path.join(app.instance_path, 'notes-v2.db')))
    _register_rest_endpoints(app)

    @click.command('n2/add', help='Import notes from a CSV file')
    @click.option('--expect-duplicates', default=False, show_default=True)
    @click.argument('csv_file', type=click.File('r'))
    @with_appcontext
    def n2_add(expect_duplicates, csv_file):
        add.all_from_csv(db_session, csv_file, expect_duplicates)

    app.cli.add_command(n2_add)


def load_models(current_db_path: str):
    engine = sqlalchemy.create_engine('sqlite:///' + current_db_path)

    Base.metadata.create_all(bind=engine)

    # Create a Session object and bind it to the declarative_base
    global db_session
    db_session = scoped_session(sessionmaker(autocommit=False,
                                             autoflush=False,
                                             bind=engine))

    Base.query = db_session.query_property()


def _register_rest_endpoints(app):
    notes_v2_rest_bp = Blueprint('notes-v2-rest', __name__)

    @notes_v2_rest_bp.route("/note/<int:note_id>")
    def get_note(note_id):
        n = Note.query.filter_by(note_id=escape(note_id)).one()
        return n.as_json(True)

    @notes_v2_rest_bp.route("/stats/domains")
    def get_domain_stats():
        return report.domain_stats(db_session)

    app.register_blueprint(notes_v2_rest_bp, url_prefix='/v2')
