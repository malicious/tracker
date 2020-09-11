import os
import re
from datetime import datetime
from typing import Dict

from flask import Flask, render_template
from markupsafe import escape
from sqlalchemy.orm import Query

import tasks
from tasks.models import TaskTimeScope, Task
from tasks.time_scope import TimeScope
from tracker.cli import reset_db, migrate_db, tasks_from_csv, populate_test_db
from tracker.content import content_db


def create_app(app_config_dict: Dict = None):
    app = Flask(__name__, instance_relative_config=True)
    # app.config['SQLALCHEMY_ECHO'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = \
        "sqlite:///" + \
        os.path.abspath(os.path.join(app.instance_path, 'content.db'))
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Apply debug/testing config changes, as needed
    if app_config_dict:
        app.config.update(app_config_dict)

    # Make the parent directory for our SQLite database
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    @app.route("/time_scope/<scope_str>")
    def get_time_scope(scope_str: str):
        return TimeScope(escape(scope_str)).to_json_dict()

    @app.route("/task/<task_id>")
    def get_task(task_id):
        task = Task.query \
            .filter(Task.task_id == escape(task_id)) \
            .first()

        task_time_scopes = TaskTimeScope.query \
            .filter(TaskTimeScope.task_id == escape(task_id)) \
            .all()

        return {
            "task": Task.tree_to_json(task),
            "time_scopes": [tts.time_scope_id for tts in task_time_scopes],
        }

    @app.route("/open-tasks/<scope_str>")
    def get_open_tasks(scope_str: str):
        end_time = TimeScope(escape(scope_str)).end
        query: Query = Task.query \
            .filter(Task.resolution == None) \
            .filter(Task.created_at <= end_time) \
            .order_by(Task.category, Task.created_at)

        return {"tasks": [task.to_json() for task in query.all()]}

    @app.route("/report-open-tasks")
    def report_open_tasks():
        query: Query = Task.query \
            .filter(Task.resolution == None) \
            .order_by(Task.category, Task.created_at)

        def link_replacer(mdown: str):
            return re.sub(r'\[(.+?)\]\((.+?)\)',
                          r"""[\1](<a href="\2">\2</a>)""",
                          mdown)

        ref_scope = TimeScope(datetime.now().date().strftime("%G-ww%V.%u"))
        return render_template('base.html',
                               tasks_by_scope={ref_scope: query.all()},
                               link_replacer=link_replacer)

    @app.route("/report-tasks/<scope_str>")
    def report_tasks(scope_str):
        scope = TimeScope(escape(scope_str))
        return tasks.content.report_tasks(scope)

    content_db.init_app(app)
    app.cli.add_command(reset_db)
    app.cli.add_command(migrate_db)
    app.cli.add_command(populate_test_db)
    app.cli.add_command(tasks_from_csv)
    return app
