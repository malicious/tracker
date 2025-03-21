import logging
import os
import re
from typing import Dict

from flask import Flask
from flask import send_from_directory
from markupsafe import Markup, escape

import notes_v2
import tasks
import tasks.flask

logging.basicConfig()


def create_app(settings_overrides: Dict = {}):
    app = Flask(__name__, instance_relative_config=True)
    app.config.update(settings_overrides)

    # Make the parent directory for our SQLite databases
    if not app.config['TESTING']:
        try:
            os.makedirs(app.instance_path)
        except OSError:
            pass

    @app.route('/favicon.ico')
    def favicon():
        return send_from_directory(os.path.join(app.root_path, ''),
                                   'favicon.ico', mimetype='image/vnd.microsoft.icon')

    @app.route('/apple-touch-icon.png')
    def favicon2():
        return send_from_directory(os.path.join(app.root_path, ''),
                                   'apple-touch-icon.png', mimetype='image/png')

    notes_v2.init_app(app)
    tasks.flask.init_app(app)

    try:
        from markdown_it import MarkdownIt
        md = MarkdownIt()
        md.options['breaks'] = True
        md.options['html'] = False
        md.enable('table')

        def render_comments(self, tokens, idx, options, env):
            if re.fullmatch(r'<!-- (.+) -->', tokens[idx].content):
                return re.sub(
                    r'<!-- (.+) -->',
                    f'<span class="comment">&lt;!-- \\1 --&gt;</span>',
                    tokens[idx].content,
                )

            return self.text(tokens, idx, options, env)

        md.add_render_rule("text", render_comments)

        def do_filter(text):
            return Markup(md.render(text))

        app.jinja_env.filters.setdefault('markdown', do_filter)

    except ImportError:
        def _noop_filter(text0):
            text1 = escape(text0)
            text2 = re.sub(
                r'&lt;!-- (.+) --&gt;',
                f'<span class="comment">&lt;!-- \\1 --&gt;</span>',
                str(text1),
            )
            return Markup(f'<p class="markdown-no-parser">{text2}</p>')

        app.jinja_env.filters.setdefault('markdown', _noop_filter)

    try:
        from flask_debugtoolbar import DebugToolbarExtension
        app.config['SECRET_KEY'] = '7'
        app.config['DEBUG_TB_INTERCEPT_REDIRECTS'] = False
        toolbar = DebugToolbarExtension(app)
    except ImportError:
        pass

    return app
