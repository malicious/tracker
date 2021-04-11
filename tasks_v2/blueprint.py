from flask import Blueprint, request
from flask_wtf import FlaskForm
from markupsafe import escape
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired

from tasks.time_scope import TimeScope
from . import report


tasks = Blueprint('tasks', __name__)

@tasks.route('/tasks/<task_id>')
def get_task(task_id):
    return report.report_one_task(escape(task_id))

@tasks.route('/tasks')
def report_tasks():
    page_scope = None
    try:
        parsed_scope = TimeScope(escape(request.args.get('scope')))
        parsed_scope.get_type()
        page_scope = parsed_scope
    except ValueError:
        pass

    return report.report_tasks(page_scope=page_scope)

class NameForm(FlaskForm):
    name = StringField('What is your name?', validators=[DataRequired()])
    submit = SubmitField('Submit')

