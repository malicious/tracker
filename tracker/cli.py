import click
from flask.cli import with_appcontext

import notes
from tracker.db import content_db


@click.command('import-notes')
@click.argument('csv_file', type=click.File('r'))
@with_appcontext
def notes_from_csv(csv_file):
    notes.add.import_from_csv(csv_file, content_db.session)


def init_app(app):
    app.cli.add_command(notes_from_csv)
