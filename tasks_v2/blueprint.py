from flask import Blueprint, redirect, render_template, request, url_for
from flask_wtf import FlaskForm
from markupsafe import escape
from wtforms import FloatField, StringField, SubmitField
from wtforms.validators import DataRequired, Optional

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
        category = StringField('category', validators=[Optional()])
        time_estimate = FloatField('time_estimate', validators=[Optional()])
        submit = SubmitField('Submit')

    render_kwargs = {}

    # First, check if this is actually a submitted edit
    task_form = TaskForm()
    if task_form.validate_on_submit():
        print(f"TODO: got valid form data, ignoring it ({task_form.desc.data}, {task_form.category.data}, {task_form.time_estimate.data})")
        return redirect(url_for('.edit_task', task_id=escape(task_id)))

    render_kwargs["task_form"] = task_form

    # Otherwise, populate the form with Task info
    task = Task.query.filter(Task.task_id == escape(task_id)).one_or_none()
    render_kwargs["task"] = task

    json_link = url_for('.get_task', task_id=escape(task_id))
    render_kwargs["json_link"] = json_link

    return render_template('task_edit.html', **render_kwargs)


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
