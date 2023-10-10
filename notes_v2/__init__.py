import hashlib
import os
from datetime import datetime
from json import JSONEncoder

import click
import sqlalchemy
from flask import Blueprint, redirect, request, url_for
from flask.cli import with_appcontext
from flask.json.provider import DefaultJSONProvider
from markupsafe import escape
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.pool import NullPool

from notes_v2 import add, report
from notes_v2.models import Base, Note
from notes_v2.time_scope import TimeScope
# noinspection PyUnresolvedReferences
from . import models

db_session = None


def load_models(current_db_path: str):
    engine = sqlalchemy.create_engine(
        'sqlite:///' + current_db_path,
        connect_args={
            "check_same_thread": False,
        },
        # NB This breaks pytests.
        poolclass=NullPool,
    )
    Base.metadata.create_all(bind=engine)

    global db_session
    db_session = scoped_session(sessionmaker(autocommit=False,
                                             autoflush=False,
                                             bind=engine))

    # TODO: Stop using the .query attribute, in favor of new SQLAlchemy 2.0 API model.
    Base.query = db_session.query_property()


def load_models_pytest():
    engine = sqlalchemy.create_engine('sqlite:///')
    Base.metadata.create_all(bind=engine)

    global db_session
    db_session = scoped_session(sessionmaker(autocommit=False,
                                             autoflush=False,
                                             bind=engine))

    # TODO: Stop using the .query attribute, in favor of new SQLAlchemy 2.0 API model.
    Base.query = db_session.query_property()


def init_app(app):
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

    @click.command('n2/update', help='Update notes from partially-imported CSV file(s)')
    @click.argument('csv_files', type=click.File('r'), nargs=-1)
    @with_appcontext
    def n2_update(csv_files):
        for csv_file in csv_files:
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

    @click.command('n2/color', help='Check render colors for different domains')
    @click.argument('domains', nargs=-1)
    @with_appcontext
    def n2_domain_colors(domains):
        for domain in domains:
            domain_hash = hashlib.sha256(domain.encode('utf-8')).hexdigest()
            print(f'"{domain}" => {int(domain_hash[0:4], 16)} => {report.render.domain_to_css_color(domain)}')
            print()
            print("If this is a contact name, check one of the following hashes:")
            if domain[0:3] == "人: ":
                domain_no_prefix = domain[3:]
                domain_no_prefix_hash = hashlib.sha256(domain_no_prefix.encode("utf-8")).hexdigest()
                print(f'"{domain_no_prefix}" => "人: [{domain_no_prefix_hash[0:11]}]"')

                dnp_to_initial_caps = domain_no_prefix.title()
                if dnp_to_initial_caps != domain_no_prefix:
                    dnp_to_initial_caps_hash = hashlib.sha256(dnp_to_initial_caps.encode("utf-8")).hexdigest()
                    print(f'"{dnp_to_initial_caps}" => "人: [{dnp_to_initial_caps_hash[0:11]}]"')

                dnp_to_lower = domain_no_prefix.lower()
                if dnp_to_lower != domain_no_prefix:
                    dnp_to_lower_hash = hashlib.sha256(dnp_to_lower.encode("utf-8")).hexdigest()
                    print(f'"{dnp_to_lower}" => "人: [{dnp_to_lower_hash[0:11]}]"')

            else:
                domain_to_initial_caps = domain.title()
                domain_to_initial_caps_hash = hashlib.sha256(domain_to_initial_caps.encode("utf-8")).hexdigest()
                print(f'"{domain_to_initial_caps}" => "人: [{domain_to_initial_caps_hash[0:11]}]"')

                domain_to_lower = domain.lower()
                domain_to_lower_hash = hashlib.sha256(domain_to_lower.encode("utf-8")).hexdigest()
                print(f'"{domain_to_lower}" => "人: [{domain_to_lower_hash[0:11]}]"')

    app.cli.add_command(n2_domain_colors)


def _register_endpoints(app):
    notes_v2_bp = Blueprint('notes-v2', __name__)

    @notes_v2_bp.route("/notes/<int:note_id>")
    def do_render_one_note(note_id):
        n = Note.query.filter_by(note_id=note_id).one()
        return report.edit_notes_simple(n, n)

    @notes_v2_bp.route("/notes")
    def do_render_matching_notes():
        page_scopes = [escape(arg) for arg in request.args.getlist('scope')]
        page_domains = [arg for arg in request.args.getlist('domain')]

        # Special arg to show recent weeks
        if page_scopes == ['week']:
            this_week = datetime.now().strftime("%G-ww%V")
            return redirect(url_for(".do_render_matching_notes", scope=this_week, domain=page_domains))

        disable_inlining = request.args.get('disable_inlining')

        return report.render_matching_notes(page_domains, page_scopes, disable_inlining)

    @notes_v2_bp.route("/note-domains")
    def do_render_note_domains():
        limit = request.args.get('limit')
        def nd_limiter(query):
            if limit:
                return query.limit(limit)
            else:
                return query

        return report.render_note_domains(db_session, nd_limiter)

    @notes_v2_bp.route("/svg.day/<day_scope>")
    def do_render_svg_day(day_scope):
        domains = [arg for arg in request.args.getlist('domain')]
        return report.standalone_render_day_svg(TimeScope(day_scope), domains, request.args.get('disable_caching'))

    @notes_v2_bp.route("/svg.week/<week_scope>")
    def do_render_svg_week(week_scope):
        domains = [arg for arg in request.args.getlist('domain')]
        return report.standalone_render_week_svg(TimeScope(week_scope), domains, request.args.get('disable_caching'))

    app.register_blueprint(notes_v2_bp, url_prefix='')


def _register_rest_endpoints(app):
    notes_v2_rest_bp = Blueprint('notes-v2-rest', __name__)

    # Add JSON encoder to handle Note types
    class NoteProvider(DefaultJSONProvider):
        @staticmethod
        def default(obj):
            if isinstance(obj, Note):
                return obj.as_json(include_domains=True)
            else:
                return DefaultJSONProvider.default(obj)

    # TODO: Make sure this doesn't stomp on other JSON encoders
    app.json_provider_class = NoteProvider
    app.json = NoteProvider(app)

    @notes_v2_rest_bp.route("/notes/<int:note_id>")
    def do_get_one_note(note_id):
        n = Note.query.filter_by(note_id=escape(note_id)).one()
        return n.as_json(True)

    @notes_v2_rest_bp.route("/notes")
    def do_get_notes():
        page_scopes = [escape(arg) for arg in request.args.getlist('scope')]
        page_domains = [escape(arg) for arg in request.args.getlist('domain')]
        return report.notes_json_tree(page_domains, page_scopes)

    @notes_v2_rest_bp.route("/note-domains")
    def do_get_note_domains():
        return report.domain_stats(db_session)

    app.register_blueprint(notes_v2_rest_bp, url_prefix='/v2')

