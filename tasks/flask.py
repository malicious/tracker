import os

from flask import Flask

from tasks.database import load_v2_models
from tasks.flask_routes import _register_endpoints, _register_rest_endpoints


def init_app(app: Flask):
    if not app.config['TESTING']:
        load_v2_models(os.path.abspath(os.path.join(app.instance_path, 'tasks-v2.db')))

    _register_endpoints(app)
    _register_rest_endpoints(app)
