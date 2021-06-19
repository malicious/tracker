import json
from datetime import datetime
from pprint import pprint, pformat
from typing import Optional, List

from sqlalchemy.exc import IntegrityError, StatementError

from tasks_v1.models import Task as Task_v1, TaskTimeScope
from tasks_v1.time_scope import TimeScope
from tasks_v2.models import Task as Task_v2, TaskLinkage

MIGRATION_BATCH_SIZE = 50


def _force_day_scope(scope_str):
    maybe_scope = TimeScope(scope_str)
    if maybe_scope.type == TimeScope.Type.quarter:
        # Convert "quarter" scopes into their first day
        scope = maybe_scope.start.strftime("%G-ww%V.%u")
        return scope
    elif maybe_scope.type == TimeScope.Type.week:
        # Convert "week" scopes into their first day
        scope = maybe_scope.start.strftime("%G-ww%V.%u")
        return scope

    return scope_str


def _get_scopes(t: Task_v1):
    tts_query = TaskTimeScope.query \
        .filter_by(task_id=t.task_id) \
        .order_by(TaskTimeScope.time_scope_id)

    return [_force_day_scope(tts.time_scope_id) for tts in tts_query.all()]


def _construct_linkages(t1: Task_v1, t2: Task_v2):
    """
    Turn TaskTimeScopes and child tasks into TaskLinkages
    """
    draft_linkages = {}

    # Add all scopes attached to Task_v1
    t1_scopes = _get_scopes(t1)
    for index, scope in enumerate(t1_scopes):
        tl = TaskLinkage(task_id=t2.task_id, time_scope_id=scope)
        tl.created_at = datetime.now()
        draft_linkages[scope] = tl
    del index, scope

    # Put resolution info into final scope
    tl_final = draft_linkages[t1_scopes[-1]]
    tl_final.resolution = t1.resolution
    tl_final.time_elapsed = t1.time_actual
    del tl_final
    del t1_scopes

    # Case: unclear, gonna do our best
    def parse_child(child_task: Task_v1):
        child_task_scopes = _get_scopes(child_task)
        if len(child_task_scopes) < 1:
            raise ValueError(f"ERROR: Task #{child_task.task_id} has no associated scopes")

        should_populate_first_scope = child_task_scopes[0] not in draft_linkages

        # Create a new linkage for each new child scope
        for index, scope in enumerate(child_task_scopes):
            if not scope in draft_linkages:
                tl = TaskLinkage(task_id=t2.task_id, time_scope_id=scope)
                tl.created_at = datetime.now()
                draft_linkages[scope] = tl
        del index, scope

        # Then, dump all the child task info into the first associated scope
        info_string = child_task.desc

        if child_task.resolution != "info":
            # Meld the resolution + desc into the TaskLinkage's resolution info
            info_string = f"({child_task.resolution}) {child_task.desc}"

        if not child_task.resolution:
            # TODO: We might be able to just leave this open
            raise ValueError(
                f"ERROR: Task #{t1.task_id} has child #{child_task.task_id} still open, must be resolved manually")

        # Set or append the info string
        tl_0 = draft_linkages[child_task_scopes[0]]
        if not tl_0.detailed_resolution:
            tl_0.detailed_resolution = info_string
        else:
            # If multiple child tasks existed, append info
            if tl_0.detailed_resolution[0:2] != "- ":
                tl_0.detailed_resolution = f"- {tl_0.detailed_resolution}"
            tl_0.detailed_resolution = f"{tl_0.detailed_resolution}\n- {info_string}"

        del info_string

        # Update accessory fields, if we can
        if should_populate_first_scope:
            tl_0.created_at = child_task.created_at

        if child_task.time_actual:
            if tl_0.time_elapsed:
                tl_0.time_elapsed += child_task.time_actual
            else:
                tl_0.time_elapsed = child_task.time_actual

    def add_child_tasks(t1: Task_v1):
        for child in t1.children:
            # print(f"DEBUG: evaluating child #{child.task_id}")
            parse_child(child)
            add_child_tasks(child)

    add_child_tasks(t1)

    # Done with initial import pass, add additional info
    draft_linkages_sorted = sorted(draft_linkages.items())
    for index, (scope, tl) in enumerate(draft_linkages_sorted):
        # attempt to fill in "roll =>" entries (skip the last entry in the set, though)
        if index < len(draft_linkages_sorted) - 1:
            if not tl.resolution:
                tl.resolution = f"roll => {draft_linkages_sorted[index + 1][0]}"

        # in the final entry in the set, dump t1's complete JSON
        elif index == len(draft_linkages_sorted) - 1:
            if tl.detailed_resolution:
                # NB This happens for 129 of 800 tasks in sample data, don't throw
                print(f"WARN: Task {t1.task_id} already has a detailed_resolution, skipping JSON dump")
            else:
                tl.detailed_resolution = json.dumps(t1.as_json(), indent=4)

        # add "migrated from" note, where applicable
        if not tl.detailed_resolution:
            tl.detailed_resolution = f"migrated from Task_v1 #{t1.task_id}"
    del index, scope, tl

    # Sometimes child tasks have scopes that extend out past the parent
    final_linkage = draft_linkages_sorted[-1][1]
    if t1.resolution and not final_linkage.resolution:
        print(
            f"WARN: task #{t1.task_id} imported, but final child scope {final_linkage.time_scope_id} is later than final parent scope {t1.first_scope}")
    del final_linkage

    return draft_linkages


def _migrate_simple(session, t1: Task_v1) -> Task_v2:
    """
    Migrate an orphan task

    Task_v1 only has a few fields that will turn into linkages:

    - for first_scope, we can add the `created_at` field,
      and possibly an `as_json()` dump
    - for the last scope, we set `resolution` + `time_elapsed`
    - every other linkage has no info, a `roll => wwXX.Y` resolution at most

    Note that first_scope isn't guaranteed to be the _earliest_ scope,
    it's intended to be the one where the task was created.
    """
    t2 = Task_v2(desc=t1.desc, category=t1.category, time_estimate=t1.time_estimate)
    session.add(t2)
    session.flush()

    created_at_linkage = None
    prior_linkage = None
    for scope_id in _get_scopes(t1):
        linkage = TaskLinkage(task_id=t2.task_id, time_scope_id=scope_id)
        linkage.created_at = datetime.now()
        session.add(linkage)

        if scope_id == _force_day_scope(t1.first_scope):
            created_at_linkage = linkage
            created_at_linkage.created_at = t1.created_at
            created_at_linkage.detailed_resolution = pformat(t1.as_json())

        # Append "roll => wwXX.Y" resolution to prior linkage
        if prior_linkage:
            min_scope_id = TimeScope(t1.first_scope).minimize(scope_id)
            prior_linkage.resolution = f"roll => {min_scope_id}"

        prior_linkage = linkage

    # For the final linkage, inherit any/all Task_v1 fields
    final_linkage = prior_linkage if prior_linkage else created_at_linkage
    final_linkage.resolution = t1.resolution
    final_linkage.time_elapsed = t1.time_actual

    return t2


def _migrate_shallow_tree(session, t1: Task_v1) -> Task_v2:
    """
    Merge a Task, its scopes, and its child Tasks

    Key thing is to treat linkages as the data object, and then dedupe them
    when it's closer to DB commit time. We're merging them via markdown
    formatting anyway, it's not like there's a ton of special data.

    A few interacting cases, documented in pytest:

    - parent task can have multiple scopes; this is the same as _migrate_simple
    - child tasks can have multiple scopes, which can overlap and interleave in time
      with the parent linkages, and even resolution.
    """
    t2 = Task_v2(desc=t1.desc, category=t1.category, time_estimate=t1.time_estimate)
    session.add(t2)
    session.flush()

    new_linkages = []
    for scope_id in _get_scopes(t1):
        linkage = TaskLinkage(task_id=t2.task_id, time_scope_id=scope_id)
        session.add(linkage)
        new_linkages.append(linkage)

        linkage.created_at = datetime.now()

        # Append "roll => XX.Y" resolution to older linkages
        if new_linkages:
            new_linkages[-1].resolution = f"roll => {linkage.time_scope_id}"

    for child_task in t1.children:
        for child_scope_id in _get_scopes(child_task):
            linkage = TaskLinkage(task_id=t2.task_id, time_scope_id=child_scope_id)

    raise ValueError(f"Failed to migrate {t1}, childed tasks not supported")


def _migrate_tree(session, t1: Task_v1) -> Task_v2:
    raise ValueError(f"Failed to migrate {t1}, childed tasks not supported")


def _do_one(tasks_v2_session, t1: Task_v1) -> Task_v2:
    def _task_depth(t: Task_v1) -> int:
        """
        Returns number of layers in task tree, where childless node = 0

        - task with children = depth 1
        - task with children with children = depth 2
        """
        t_depth = 0
        for child in t.children:
            t_depth = max(t_depth, _task_depth(child) + 1)

        return t_depth

    baseline_t2 = Task_v2.query \
        .filter_by(desc=t1.desc) \
        .one_or_none()
    if baseline_t2:
        raise NotImplementedError("Can't handle tasks with duplicate descriptions")

    if not t1.parent and not t1.children:
        return _migrate_simple(tasks_v2_session, t1)

    if not t1.parent and t1.children:
        if _task_depth(t1) > 1:
            return _migrate_tree(tasks_v2_session, t1)
        else:
            return _migrate_shallow_tree(tasks_v2_session, t1)


def do_one(tasks_v2_session, t1: Task_v1) -> Optional[Task_v2]:
    if t1.parent:
        return None

    try:
        t2 = _do_one(tasks_v2_session, t1)
    except ValueError as e:
        print(e)
        pprint(t1.as_json())
        raise

    try:
        tasks_v2_session.commit()
    except StatementError as e:
        tasks_v2_session.rollback()
        print(f"ERROR: Hit exception while parsing {t1}, skipping")
        print()
        print(e)
        print()
        pprint(t1.as_json())
        raise
    except IntegrityError as e:
        session.rollback()
        print(f"ERROR: Hit exception while parsing {t1}, skipping")
        print()
        print(e)
        print()
        pprint(t1.as_json())
        raise

    return t2


def do_multiple(tasks_v1_session,
                tasks_v2_session,
                force_delete_current: bool = False):
    if force_delete_current:
        tasks_v2_session.query(TaskLinkage).delete()
        tasks_v2_session.query(Task_v2).delete()
        tasks_v2_session.commit()

    v1_tasks = Task_v1.query \
        .order_by(Task_v1.task_id) \
        .all()
    for t1 in v1_tasks:
        do_one(tasks_v2_session, t1)

    print("Done migrating tasks")
