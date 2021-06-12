from typing import Dict

from flask import Flask

import notes
import tasks_v1
import tasks_v2
from . import cli, db


def create_app(settings_overrides: Dict = {}):
    app = Flask(__name__, instance_relative_config=True)
    db.init_app(app, settings_overrides)
    notes.init_app(app)
    tasks_v1.init_app(app)
    tasks_v2.init_app(app)
    cli.init_app(app)

    try:
        from flask_debugtoolbar import DebugToolbarExtension

        app.config['SECRET_KEY'] = '7'
        toolbar = DebugToolbarExtension(app)
    except ImportError:
        pass

    return app
