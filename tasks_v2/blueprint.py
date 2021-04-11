from flask import Blueprint, render_template, request
from flask_wtf import FlaskForm
from markupsafe import escape
from wtforms import FloatField, StringField, SubmitField
from wtforms.validators import DataRequired

from tasks.time_scope import TimeScope
from . import report
from .models import Task


tasks = Blueprint('tasks', __name__)

@tasks.route('/tasks/<task_id>')
def get_task(task_id):
    return report.report_one_task(escape(task_id))


@tasks.route('/tasks/<task_id>/edit', methods=['GET', 'POST'])
def edit_task(task_id):
    class TaskForm(FlaskForm):
        desc = StringField('desc', validators=[DataRequired()])
        category = StringField('category')
        time_estimate = FloatField('time_estimate')
        submit = SubmitField('Submit')

    # First, check if this is actually a submitted edit
    task_form = TaskForm()
    if task_form.validate_on_submit():
        print("TODO: got valid form data, ignoring it")
        return redirect(url_for('.edit_task', task_id=task_id))

    # Otherwise, populate the form with Task info
    task = Task.query.filter(Task.task_id == task_id).one_or_none()
    return render_template('task_edit.html', task_form=TaskForm(), task=task)


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
