import os
from typing import Dict

import click
from flask import Flask
from flask.cli import with_appcontext
from flask_sqlalchemy import SQLAlchemy


@click.command('create-db')
@with_appcontext
def create_db():
    content_db.create_all()


@click.command('reset-db')
@with_appcontext
def reset_db():
    content_db.drop_all()
    content_db.create_all()


def init_app(app: Flask, settings_overrides: Dict):
    app.config['SQLALCHEMY_BINDS'] = {
        'notes': 'sqlite:///' + os.path.abspath(os.path.join(app.instance_path, 'notes.db')),
        'tasks': 'sqlite:///' + os.path.abspath(os.path.join(app.instance_path, 'tasks.db')),
    }
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Apply debug/testing config changes, as needed
    app.config.update(settings_overrides)

    # Make the parent directory for our SQLite database
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    content_db.init_app(app)
    app.cli.add_command(create_db)
    app.cli.add_command(reset_db)


content_db = SQLAlchemy()
