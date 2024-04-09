import hashlib
import os
import re
from datetime import datetime, timedelta

import click
import sqlalchemy
from flask import Blueprint, redirect, request, url_for
from flask.cli import with_appcontext
from flask.json.provider import DefaultJSONProvider
from markupsafe import escape
from sqlalchemy import func
from sqlalchemy.orm import scoped_session, sessionmaker, Session
from sqlalchemy.pool import NullPool

import notes_v2.report
from notes_v2 import add, report
from notes_v2.models import Base, Note, NoteDomain
from util import TimeScope, TimeScopeBuilder
# noinspection PyUnresolvedReferences
from . import models

db_session: Session | None = None


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


def strtobool(val) -> bool:
    """
    Formerly distutils.util.strtobool(), deprecated in Python 3.10
    """
    if val is None or val.lower() in ('none',):
        return False
    elif val.lower() in ('y', 'yes', 't', 'true', 'on', '1'):
        return True
    elif val.lower() in ('n', 'no', 'f', 'false', 'off', '0'):
        return False
    else:
        raise ValueError(f"unrecognized bool-value {val}")


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

    app.cli.add_command(n2_update)

    @click.command('n2/export', help='Export all notes as CSV output')
    @click.option('--write-note-id/--skip-note-id', default=False, show_default=True)
    @with_appcontext
    def n2_export(write_note_id):
        add.all_to_csv(write_note_id=write_note_id)

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
        page_scopes = tuple(escape(arg) for arg in request.args.getlist('scope'))
        single_page = strtobool(request.args.get('single_page'))

        url_kwargs = {
            'domain': tuple(request.args.getlist('domain')),
        }
        if single_page:
            url_kwargs['single_page'] = single_page

        if page_scopes == ('week',):
            url_kwargs['scope'] = datetime.now().strftime("%G-ww%V")
            return redirect(url_for(".do_render_matching_notes", **url_kwargs))
        elif page_scopes == ('day',):
            url_kwargs['scope'] = datetime.now().strftime("%G-ww%V.%u")
            return redirect(url_for(".do_render_matching_notes", **url_kwargs))
        # Year-scopes get broken up into four quarters
        elif len(page_scopes) == 1:
            m = re.fullmatch(r'\d\d\d\d', page_scopes[0])
            if m:
                url_kwargs['scope'] = [escape(f"{m[0]}—Q{quarter}") for quarter in range(1,5)]
                return redirect(url_for(".do_render_matching_notes", **url_kwargs))

        return report.render_matching_notes(
            db_session,
            url_kwargs['domain'],
            page_scopes,
            single_page,
        )

    @notes_v2_bp.route("/domains")
    def do_render_domains():
        limit = request.args.get('limit')
        sql_ilike_filter = request.args.get('filter')

        def nd_limiter(query):
            if limit:
                query = query.limit(limit)
            if sql_ilike_filter:
                full_sql_filter = f"%{sql_ilike_filter}%"
                query = query.filter(NoteDomain.domain_id.ilike(full_sql_filter))

            return query

        return notes_v2.report.domains.render_stats(db_session, nd_limiter)

    @notes_v2_bp.route("/domains/recent")
    def do_render_recent_domains():
        def nd_limiter(query, cutoff_days: int = 90):
            early_cutoff = datetime.now() - timedelta(days=cutoff_days)
            early_cutoff_ts = TimeScopeBuilder.day_scope_from_dt(early_cutoff)

            # TODO: Modify the query so `func.count(Note.note_id)` goes past the cutoff.
            #       For now, it only reports the number of notes in the last 90 days.
            return query.where(Note.time_scope_id >= early_cutoff_ts)

        return notes_v2.report.domains.render_stats(db_session, nd_limiter)

    @notes_v2_bp.route("/domains/calendar")
    def do_render_domain_calendar():
        """
        The difference between domains and filters is that a `filter` will lump together all matching notes.

        TODO: Preserve relative ordering of domains and filters.
        """
        page_domains = tuple(escape(arg) for arg in request.args.getlist('domain') or [])
        page_domain_filters = tuple(escape(arg) for arg in request.args.getlist('filter') or [])
        if not page_domains and not page_domain_filters:
            return {"error": "Must provide domain filters, because we're not rendering every note"}

        return notes_v2.report.counts.render_calendar(db_session, page_domains, page_domain_filters)

    @notes_v2_bp.route("/domains/calendar/<string:sql_ilike_filter>")
    def do_render_one_domain_calendar(sql_ilike_filter: str):
        page_domain_filter = str(escape(sql_ilike_filter))
        if not page_domain_filter:
            return {"error": "Must provide domain filter, because we're not rendering every note"}

        return notes_v2.report.counts.render_one_calendar(db_session, page_domain_filter)

    @notes_v2_bp.route("/svg.day/<day_scope>")
    def do_render_svg_day(day_scope):
        return report.standalone_render_day_svg(
            db_session,
            tuple(request.args.getlist('domain')),
            TimeScope(day_scope),
            strtobool(request.args.get('disable_caching')),
        )

    @notes_v2_bp.route("/svg.week/<week_scope>")
    def do_render_svg_week(week_scope):
        return report.standalone_render_week_svg(
            db_session,
            tuple(request.args.getlist('domain')),
            TimeScope(week_scope),
            strtobool(request.args.get('disable_caching')),
        )

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
        return report.notes_json_tree(db_session, page_domains, page_scopes)

    @notes_v2_rest_bp.route("/domains")
    def do_get_note_domains():
        return notes_v2.report.domains.stats(db_session)

    @notes_v2_rest_bp.route("/domains/calendar")
    def do_get_note_domains_calendar():
        page_scopes = tuple(escape(arg) for arg in request.args.getlist('scope') or [])
        page_domain_filters = tuple(escape(arg) for arg in request.args.getlist('filter') or [])
        return notes_v2.report.counts.calendar(db_session, page_scopes, page_domain_filters)

    app.register_blueprint(notes_v2_rest_bp, url_prefix='/v2')
