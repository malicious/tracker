from flask import Flask

from tracker.scope import TimeScope


def create_app():
    app = Flask(__name__)

    @app.route("/time_scope/<scope_str>")
    def print_time_scope(scope_str: str):
        return TimeScope(scope_str).to_json_dict()

    return app
