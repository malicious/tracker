import os
from typing import Dict

from flask import Flask
from flask_sqlalchemy import SQLAlchemy


def init_app(app: Flask, settings_overrides: Dict):
    app.config['SQLALCHEMY_DATABASE_URI'] = \
        "sqlite:///" + \
        os.path.abspath(os.path.join(app.instance_path, 'content.db'))
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Apply debug/testing config changes, as needed
    app.config.update(settings_overrides)

    # Make the parent directory for our SQLite database
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    content_db.init_app(app)


content_db = SQLAlchemy()
