import os

import sqlalchemy
from flask import Flask, Blueprint
from sqlalchemy.orm import scoped_session, sessionmaker

# noinspection PyUnresolvedReferences
from . import models
from .models import Base, Task

db_session = None


def init_app(app: Flask):
    if not app.config['TESTING']:
        load_v2_models(os.path.abspath(os.path.join(app.instance_path, 'tasks-v2.db')))

        @app.teardown_request
        def remove_session(ex=None):
            global db_session
            if db_session:
                db_session.remove()
                db_session = None

    _register_endpoints(app)
    _register_rest_endpoints(app)


def load_v2_models(current_db_path: str):
    engine = sqlalchemy.create_engine('sqlite:///' + current_db_path)

    Base.metadata.create_all(bind=engine)

    # Create a Session object and bind it to the declarative_base
    global db_session
    if db_session:
        print("WARN: db_session already exists, creating a new one anyway")
        db_session = None

    db_session = scoped_session(sessionmaker(autocommit=False,
                                             autoflush=False,
                                             bind=engine))

    Base.query = db_session.query_property()


def _register_endpoints(app: Flask):
    tasks_v2_bp = Blueprint('tasks-v2', __name__)

    @tasks_v2_bp.route("/browse")
    def report_tasks():
        pass

    app.register_blueprint(tasks_v2_bp)


def _register_rest_endpoints(app: Flask):
    tasks_v2_rest_bp = Blueprint('tasks-v2-rest', __name__)

    @tasks_v2_rest_bp.route("/task")
    def create_task():
        pass

    @tasks_v2_rest_bp.route("/task/<int:task_id>")
    def get_task(task_id):
        task: Task = Task.query \
            .filter_by(task_id=task_id) \
            .one_or_none()
        if not task:
            return {"error": f"invalid task_id: {task_id}"}

        return task.as_json()

    @tasks_v2_rest_bp.route("/task/<int:task_id>/edit", methods=['GET', 'POST'])
    def edit_task(task_id):
        pass

    @tasks_v2_rest_bp.route("/tasks")
    def get_all_tasks():
        pass

    app.register_blueprint(tasks_v2_rest_bp, url_prefix='/v2')
