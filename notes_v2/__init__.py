import os

import click
from flask.cli import with_appcontext
import sqlalchemy
from sqlalchemy.orm import scoped_session, sessionmaker

from notes_v2 import add
from notes_v2.models import Base
# noinspection PyUnresolvedReferences
from . import models

db_session = None


def init_app(app):
    if not app.config['TESTING']:
        load_models(os.path.abspath(os.path.join(app.instance_path, 'notes-v2.db')))

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
