import logging
from datetime import datetime

from dateutil import parser
from sqlalchemy import select

from tasks.database import TasksDB
from tasks.database_models import Task, TaskLinkage

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def _attribute_renamer(form_data_attribute: str) -> str:
    # Fyi this function used to translate the names, but we can put underscores
    # into HTML5 form data. For now, this is something like a typing function,
    # and should be replaced with Pydantic.
    #
    # return form_data_attribute.replace('-', '_')
    return form_data_attribute


def _update_task_only(
        task: Task,
        form_data,
        default_import_source: str = '',
):
    """
    This function is called on creation on any Task through the web UI.

    It translates web form data into Tasks, and also sanitizes that output,
    since I can't figure out `NULL` and `None` and `"None"`.
    """
    # First, check if any of the Task data was updated
    for form_data_attribute in ['desc', 'desc_for_llm', 'category', 'import_source', 'time_estimate']:
        attribute = _attribute_renamer(form_data_attribute)
        if f'task-{form_data_attribute}' not in form_data:
            raise ValueError(f"Couldn't find {task}.{attribute} in HTTP form data")

        # If the value's empty, we're probably trying to clear it
        if not form_data[f'task-{form_data_attribute}']:
            if getattr(task, attribute):
                logger.debug(f"clearing {task}.{attribute} to None")
            setattr(task, attribute, None)

        # If it's different, try setting it
        elif form_data[f'task-{form_data_attribute}'] != getattr(task, attribute):
            logger.debug(f"updating {task}.{attribute} to {form_data[f'task-{form_data_attribute}']}")
            setattr(task, attribute, form_data[f'task-{form_data_attribute}'])

    # We explicitly specify import_source because in SQLite, primary key's can't/shouldn't be NULL.
    # And there's a very tortured path from UI data to database, so just set it here.
    if not task.import_source:
        logger.info(f"re-setting {task}.import_source to {repr(default_import_source)} "
                    f"instead of {repr(task.import_source)}")
        task.import_source = default_import_source


def _update_linkage_only(
        tl: TaskLinkage,
        tl_ts: str,
        form_data,
        parent_import_source: str,
):
    """
    This function is called on any creation or modification through the web UI.
    """
    # Update fields
    for field in ['created_at', 'time_elapsed', 'resolution', 'detailed_resolution']:
        if f'tl-{tl_ts}-{field}' not in form_data:
            raise ValueError(f"Couldn't find {tl}.{field} in HTTP form data")

        if not form_data[f'tl-{tl_ts}-{field}']:
            if getattr(tl, field):
                logger.debug(f"clearing {tl}.{field} to None")
            setattr(tl, field, None)

        # If it's different, try setting it
        elif form_data[f'tl-{tl_ts}-{field}'] != getattr(tl, field):
            if field == 'time_scope_id' and str(tl.time_scope_id) != form_data[f'tl-{tl_ts}-{field}']:
                raise ValueError(f"Can't change time_scope_id yet")
            if field == 'created_at' and form_data[f'tl-{tl_ts}-{field}'] == 'None':
                tl.created_at = None
            elif field == 'created_at':
                new_value = parser.parse(form_data[f'tl-{tl_ts}-{field}'])
                if new_value != tl.created_at:
                    if getattr(tl, field):
                        logger.debug(
                            f"updating {tl}.{field} to {new_value}, "
                            f"was: {getattr(tl, field)} (delta of {new_value - getattr(tl, field)})")
                    else:
                        logger.debug(
                            f"updating {tl}.{field} to {new_value}, "
                            f"was: {getattr(tl, field)}")
                    setattr(tl, field, new_value)
                del new_value
            elif getattr(tl, field) != form_data[f'tl-{tl_ts}-{field}']:
                setattr(tl, field, form_data[f'tl-{tl_ts}-{field}'])

    # And propagate the Task.import_source, if needed
    tl.import_source = parent_import_source


def create_task(session, form_data):
    task = Task()
    session.add(task)

    _update_task_only(task, form_data)
    session.flush()

    update_task(session, task.task_id, form_data)
    return task


def update_task(session: TasksDB, task_id, form_data):
    # TODO: As-is, if this field was edited, we don't know what the original entry was.
    #       For now, make this field read-only in the web form.
    provided_import_source = form_data['task-import_source']
    task: Task = session.execute(
        select(Task)
        .filter_by(task_id=task_id, import_source=provided_import_source)
    ).scalar_one()

    _update_task_only(task, form_data)

    session.add(task)
    session.flush()

    # Update the entire set of linkages, and ensure they match the ones stored in Task
    existing_tls = list(task.linkages)

    # Key on `-time_scope_id` to identify valid linkages
    form_tl_ids = [key[3:-14] for (key, value) in form_data.items(multi=True) if key[-14:] == "-time_scope_id"]
    form_tl_times = [form_data[f'tl-{form_tl_id}-time_scope_id'] for form_tl_id in form_tl_ids]
    if len(form_tl_ids) != len(set(form_tl_times)):
        duplicate_tl_times = list(form_tl_times)
        for tl_time in set(form_tl_times):
            duplicate_tl_times.remove(tl_time)

        raise ValueError(f"Found several TaskLinkages with duplicate time_scope_id's, erroring: {duplicate_tl_times}")

    for form_tl_id in form_tl_ids:
        tl_ts_raw = form_data[f'tl-{form_tl_id}-time_scope_id']
        tl_ts = datetime.strptime(tl_ts_raw, '%G-ww%V.%u').date()

        # Check if TL even exists
        tl: TaskLinkage = TaskLinkage.query \
            .filter_by(task_id=task_id, import_source=provided_import_source, time_scope=tl_ts) \
            .one_or_none()
        if not tl:
            tl = TaskLinkage(task_id=task_id, import_source=provided_import_source, time_scope=tl_ts)

        _update_linkage_only(tl, form_tl_id, form_data, task.import_source)

        session.add(tl)

        if tl in existing_tls:
            existing_tls.remove(tl)
        else:
            logger.info(f"added new tl {tl}")
        del tl

    if existing_tls:
        logger.info(f"{len(existing_tls)} linkages to be removed, {existing_tls}")
    for tl in existing_tls:
        session.delete(tl)

    # Done, commit everything
    session.commit()
