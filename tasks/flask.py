import os

from flask import Flask

from tasks.database import load_database_models, migrate_v2_models
from tasks.flask_routes import _register_endpoints, _register_rest_endpoints


def init_app(app: Flask) -> None:
    should_load_database_models: bool = True
    if app.config['TESTING']:
        should_load_database_models = False

    if should_load_database_models:
        db_path = os.path.abspath(os.path.join(app.instance_path, 'tasks-v3.db'))
        v2_db_path = os.path.abspath(os.path.join(app.instance_path, 'tasks-v2.db'))

        if (
                not os.path.exists(db_path)
                and os.path.exists(v2_db_path)
        ):
            migrate_v2_models(db_path, v2_db_path)

        load_database_models(db_path)
        should_load_database_models = False

    _register_endpoints(app)
    _register_rest_endpoints(app)
