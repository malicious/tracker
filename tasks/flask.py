import os

import click
from flask import Flask
from flask.cli import with_appcontext

from tasks import import_export
from tasks.database import load_database_models, try_migrate_v2_models
from tasks.flask_routes import _register_endpoints, _register_rest_endpoints


def init_app(app: Flask) -> None:
    should_load_database_models: bool = True
    if app.config['TESTING']:
        should_load_database_models = False

    if should_load_database_models:
        db_path = os.path.abspath(os.path.join(app.instance_path, 'tasks-v3.db'))
        v2_db_path = os.path.abspath(os.path.join(app.instance_path, 'tasks-v2.db'))
        try_migrate_v2_models(db_path, v2_db_path)

        load_database_models(db_path)
        should_load_database_models = False

    _register_endpoints(app)
    _register_rest_endpoints(app)

    @click.command('t3/list', help='List import sources in the tasks database')
    @click.option('--sql-ilike-expr', default='%', show_default=True)
    @with_appcontext
    def t3_list(sql_ilike_expr):
        return import_export.list_import_sources(sql_ilike_expr)

    app.cli.add_command(t3_list)

    @click.command('t3/delete', help='Delete all tasks matching the given import source')
    @click.option('--sql-ilike-expr', default='%', show_default=True)
    @with_appcontext
    def t3_delete(sql_ilike_expr):
        return import_export.delete_import_source(sql_ilike_expr)

    app.cli.add_command(t3_delete)

    @click.command('t3/import', help='Import tasks from an external database')
    @click.option('--default-import-source')
    @click.option('--override-import-source')
    @click.argument('sqlite_db_path')
    @with_appcontext
    def t3_import(sqlite_db_path, default_import_source, override_import_source):
        return import_export.import_from(sqlite_db_path, default_import_source, override_import_source)

    app.cli.add_command(t3_import)

    @click.command('t3/export', help='Export tasks to an external database file')
    @click.option('--default-import-source')
    @click.option('--override-import-source')
    @click.argument('sqlite_db_path')
    @with_appcontext
    def t3_export(sqlite_db_path, default_import_source, override_import_source):
        return import_export.export_to(sqlite_db_path, default_import_source, override_import_source)

    app.cli.add_command(t3_export)
