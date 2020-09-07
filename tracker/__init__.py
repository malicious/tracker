import os
import re
from typing import Dict

from flask import Flask, render_template
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Query

from tasks import populate_test_data, tasks_from_csv, Task
from tracker.content import content_db, reset_db, migrate_db
from tracker.scope import TimeScope


# ---------
# flask app
# ---------

def create_app(app_config_dict: Dict = None):
    app = Flask(__name__, instance_relative_config=True)
    app.config['SQLALCHEMY_ECHO'] = True
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
        return TimeScope(scope_str).to_json_dict()

    @app.route("/task/<task_id>")
    def get_task(task_id):
        q: Query = Task.query.filter_by(task_id=task_id)
        try:
            t = q.first()
            if t:
                return t.to_json()
        except OperationalError:
            pass

        return {"error": f"Couldn't find task: {task_id}"}

    @app.route("/report-open-tasks")
    def report_open_tasks():
        query: Query = Task.query \
            .filter(Task.resolution == None) \
            .order_by(Task.category, Task.created_at)

        def link_replacer(mdown: str):
            return re.sub(r'\[(.+?)\]\((.+?)\)',
                          r"""[\1](<a href="\2">\2</a>)""",
                          mdown)

        return render_template('base.html',
                               tasks=query.all(), link_replacer=link_replacer)

    @app.route("/open-tasks/<scope_str>")
    def get_open_tasks(scope_str: str):
        end_time = TimeScope(scope_str).end
        query: Query = Task.query \
            .filter(Task.resolution == None) \
            .filter(Task.created_at <= end_time) \
            .order_by(Task.category, Task.created_at)

        return {"tasks": [task.to_json() for task in query.all()]}

    content_db.init_app(app)
    app.cli.add_command(reset_db)
    app.cli.add_command(migrate_db)
    app.cli.add_command(populate_test_data)
    app.cli.add_command(tasks_from_csv)
    return app
