import click
from flask.cli import with_appcontext
from flask_sqlalchemy import SQLAlchemy

content_db = SQLAlchemy()


@click.command('reset-db')
@with_appcontext
def reset_db():
    content_db.drop_all()
    content_db.create_all()



@click.command('migrate-db')
@with_appcontext
def migrate_db():
    content_db.create_all()
