import json
import re
from datetime import datetime, timedelta
from dateutil import parser
from typing import Optional

from flask import render_template, url_for

from tasks_v1.time_scope import TimeScope, TimeScopeUtils
from tasks_v2.models import Task, TaskLinkage


def _update_task_only(task, form_data):
    # First, check if any of the Task data was updated
    for attribute in ['category', 'desc', 'time_estimate']:
        if f'task-{attribute}' not in form_data:
            raise ValueError(f"Couldn't find {task}.{attribute} in HTTP form data")

        # If the value's empty, we're probably trying to clear it
        if not form_data[f'task-{attribute}']:
            if getattr(task, attribute):
                print(f"DEBUG: clearing {task}.{attribute} to None")
            setattr(task, attribute, None)

        # If it's different, try setting it
        elif form_data[f'task-{attribute}'] != getattr(task, attribute):
            print(f"DEBUG: updating {task}.{attribute} to {form_data[f'task-{attribute}']}")
            setattr(task, attribute, form_data[f'task-{attribute}'])

        # Finally, delete from the map, because we expect that map to be cleared
        #del form_data[f'task-{attribute}']


def _update_linkage_only(tl, tl_ts, form_data):
    # Update fields
    for field in ['created_at', 'time_elapsed', 'resolution', 'detailed_resolution']:
        print(f"DEBUG: Checking {tl}.{field} against \"{form_data[f'tl-{tl_ts}-{field}']}\"")
        if f'tl-{tl_ts}-{field}' not in form_data:
            raise ValueError(f"Couldn't find {tl}.{field} in HTTP form data")

        if not form_data[f'tl-{tl_ts}-{field}']:
            if getattr(tl, field):
                print(f"DEBUG: clearing {tl}.{field} to None")
            setattr(tl, field, None)

        # If it's different, try setting it
        elif form_data[f'tl-{tl_ts}-{field}'] != getattr(tl, field):
            if field == 'time_scope_id' and str(tl.time_scope_id) != form_data[f'tl-{tl_ts}-{field}']:
                raise ValueError(f"Can't change time_scope_id yet")
            # TODO: check that created_at is valid and not None at import time
            if field == 'created_at' and form_data[f'tl-{tl_ts}-{field}'] == 'None':
                tl.created_at = None
            elif field == 'created_at':
                new_value = parser.parse(form_data[f'tl-{tl_ts}-{field}'])
                if new_value != tl.created_at:
                    print(f"DEBUG: updating {tl}.{field} to {new_value}")
                    if getattr(tl, field):
                        print(f"       was: {getattr(tl, field)} (delta of {new_value - getattr(tl, field)})")
                    else:
                        print(f"       was: {getattr(tl, field)}")
                    setattr(tl, field, new_value)
                del new_value
            else:
                print(f"DEBUG: updating {tl}.{field} to \"{form_data[f'tl-{tl_ts}-{field}']}\"")
                print(f"       was: {getattr(tl, field)}")
                setattr(tl, field, form_data[f'tl-{tl_ts}-{field}'])

        # Finally, delete from the map, because we expect that map to be cleared
        #del form_data[f'tl-{tl_ts}-{field}']


def create_task(session, form_data):
    task = Task()
    session.add(task)

    _update_task_only(task, form_data)
    session.flush()

    update_task(session, task.task_id, form_data)
    return task


def update_task(session, task_id, form_data):
    #print(json.dumps(form_data.to_dict(flat=False), indent=2))

    task: Task = Task.query \
        .filter_by(task_id=task_id) \
        .one()

    _update_task_only(task, form_data)

    session.add(task)
    session.flush()


    # Update the entire set of linkages, and ensure they match the ones stored in Task
    existing_tls = list(task.linkages)

    # Key on `-time_scope_id` to identify valid linkages
    form_tl_ids = [key[3:-14] for (key, value) in form_data.items(multi=True) if key[-14:] == "-time_scope_id"]
    form_tl_times = set([parser.parse(form_data[f'tl-{form_tl_id}-time_scope_id']) for form_tl_id in form_tl_ids])
    if len(form_tl_ids) != len(form_tl_times):
        print(f"ERROR: set of form TLs, {form_tl_times}")
        raise ValueError("Found a duplicate form time, erroring")

    for form_tl_id in form_tl_ids:
        tl_ts_raw = form_data[f'tl-{form_tl_id}-time_scope_id']
        tl_ts = parser.parse(tl_ts_raw).date()

        # Check if TL even exists
        tl: TaskLinkage = TaskLinkage.query \
            .filter_by(task_id=task_id, time_scope_id=tl_ts) \
            .one_or_none()
        if not tl:
            tl = TaskLinkage(task_id=task_id, time_scope_id=tl_ts)

        _update_linkage_only(tl, form_tl_id, form_data)

        session.add(tl)

        if tl in existing_tls:
            existing_tls.remove(tl)
        else:
            print(f"DEBUG: added new tl {tl}")
        del tl

    if existing_tls:
        print(f"DEBUG: {len(existing_tls)} linkages to be removed, {existing_tls}")
    for tl in existing_tls:
        session.delete(tl)

    # Done, commit everything
    session.commit()
