import os
from typing import Dict

from flask import Flask

import notes_v2
import tasks_v1
import tasks_v2


def create_app(settings_overrides: Dict = {}):
    app = Flask(__name__, instance_relative_config=True)
    app.config.update(settings_overrides)

    # Make the parent directory for our SQLite databases
    if not app.config['TESTING']:
        try:
            os.makedirs(app.instance_path)
        except OSError:
            pass

    notes_v2.init_app(app)
    tasks_v1.init_app(app)
    tasks_v2.init_app(app)

    try:
        from flask_debugtoolbar import DebugToolbarExtension

        app.config['SECRET_KEY'] = '7'
        app.config['DEBUG_TB_INTERCEPT_REDIRECTS'] = False
        toolbar = DebugToolbarExtension(app)
    except ImportError:
        pass

    return app
