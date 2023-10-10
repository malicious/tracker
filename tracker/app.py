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
            # First, pre-escape timestamp-y comments with an extra newline
            text1 = re.sub(r'<!-- (.+) -->', f'<!-- \\1 -->\n', text)

            # Convert to HTML with the extra newline(s)
            result2 = misaka.html(
                text1,
                extensions=misaka.EXT_TABLES,
                render_flags=misaka.HTML_ESCAPE | misaka.HTML_HARD_WRAP,
            )

            # Then, un-escape that newline
            result3 = re.sub(
                r'<p>&lt;!-- (.+) --&gt;</p>\n\n<p>',
                f'<p><span class="comment">&lt;!-- \\1 --&gt;</span><br>',
                result2,
            )
            # And tag any timestamp-y comments that didn't match that pattern
            result4 = re.sub(
                r'&lt;!-- (.+) --&gt;',
                f'<span class="comment">&lt;!-- \\1 --&gt;</span>',
                result3,
            )
            return Markup(result4)

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
