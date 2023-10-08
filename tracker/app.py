import os
import re
from typing import Dict

from flask import Flask
from markupsafe import Markup

import notes_v2
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
    tasks_v2.init_app(app)

    # misaka formatting is optional because it wraps a C library + is no longer maintained
    try:
        import misaka
        def md_wrapper(text):
            result0 = misaka.html(text, extensions=0, render_flags=misaka.HTML_HARD_WRAP)
            result = re.sub(r'<!-- (.+) -->', f'<span class="comment">&lt;!-- \\1 --&gt;</span>', result0)
            return Markup(result)

        app.jinja_env.filters.setdefault('markdown', md_wrapper)

    except ImportError:
        def _noop_filter(text):
            return Markup(f'<p style="white-space: pre;">{text}</p>')

        app.jinja_env.filters.setdefault('markdown', _noop_filter)

    try:
        from flask_debugtoolbar import DebugToolbarExtension
        app.config['SECRET_KEY'] = '7'
        app.config['DEBUG_TB_INTERCEPT_REDIRECTS'] = False
        toolbar = DebugToolbarExtension(app)
    except ImportError:
        pass

    return app
