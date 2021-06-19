import json
from datetime import datetime
from pprint import pprint, pformat
from typing import Optional, List

from sqlalchemy.exc import IntegrityError, StatementError

from tasks_v1.models import Task as Task_v1, TaskTimeScope
from tasks_v1.time_scope import TimeScope
from tasks_v2.models import Task as Task_v2, TaskLinkage

MIGRATION_BATCH_SIZE = 50


def _get_scopes(t: Task_v1):
    def trim_scope(scope_str):
        maybe_scope = TimeScope(scope_str)
        if maybe_scope.type == TimeScope.Type.quarter:
            # Convert "quarter" scopes into their first day
            scope = maybe_scope.start.strftime("%G-ww%V.%u")
            print(f"INFO: task #{t.task_id} has quarter scope {scope_str}, downsizing to {scope}")
            return scope
        elif maybe_scope.type == TimeScope.Type.week:
            # Convert "week" scopes into their first day
            scope = maybe_scope.start.strftime("%G-ww%V.%u")
            print(f"INFO: task #{t.task_id} has week scope {scope_str}, downsizing to {scope}")
            return scope

        return scope_str

    tts_query = TaskTimeScope.query \
        .filter_by(task_id=t.task_id) \
        .order_by(TaskTimeScope.time_scope_id)

    return [trim_scope(tts.time_scope_id) for tts in tts_query.all()]


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


def _migrate_one(session, t1: Task_v1, print_fn):
    """
    Returns new parent task, plus count of total migrated tasks

    Expected to return None on failure, not raise exceptions
    """

    def print_task_and_children(depth, t: Task_v1):
        """
        Recursive print. Also counts the number of prints.
        """
        print_fn("    " * depth + f"- #{t.task_id}: ({t.resolution}) {t.desc}")
        print_fn("    " * depth + f"  scopes: {_get_scopes(t)}")
        task_count = 1

        for child in t.children:
            task_count += print_task_and_children(depth + 1, child)

        return task_count

    # Print Task_v1 info
    print_fn(f"importing #{t1.task_id}, old info:")
    print_fn("-" * 72)
    print_fn()
    task_v1_count = print_task_and_children(0, t1)
    print_fn()
    print_fn()

    # Check if Task_v2 already exists
    existing_t2 = Task_v2.query \
        .filter(Task_v2.desc == t1.desc) \
        .one_or_none()
    if not existing_t2:
        # Construct Task_v2
        try:
            t2 = Task_v2(desc=t1.desc,
                         category=t1.category,
                         time_estimate=t1.time_estimate)
            session.add(t2)
            session.commit()
        except StatementError as e:
            session.rollback()
            print(f"ERROR: Hit exception when parsing task #{t1.task_id}, skipping")
            print(t1.to_json_dict())
            return None, 0
        except IntegrityError as e:
            session.rollback()
            print(e)
            print(t1.to_json_dict())
            return None, 0

    print_fn("migrating to Task_v2, new info:")
    print_fn("-" * 72)
    print_fn()

    if existing_t2:
        print(f"WARN: #{t1.task_id} matches existing Task_v2 #{existing_t2.task_id}, reusing")
        t2 = existing_t2

    # Print Task_v2 info
    print_fn(f"{t2.desc}")
    print_fn()

    try:
        t2_linkages = _construct_linkages(t1, t2)
    except ValueError as e:
        print(e)
        input(f"Import failed for task #{t1.task_id}, press enter to ignore bad import and continue")
        return None, 0

    for scope, tl in sorted(t2_linkages.items()):
        print_fn(f"- {tl.time_scope_id}: {tl.resolution} / {tl.detailed_resolution}")
        session.add(tl)

    print_fn()
    print_fn()

    session.commit()
    return t2, task_v1_count


def _migrate_simple(session, t1: Task_v1) -> Task_v2:
    t2 = Task_v2(desc=t1.desc, category=t1.category, time_estimate=t1.time_estimate)
    session.add(t2)
    session.flush()

    new_linkages = []
    for scope_id in _get_scopes(t1):
        linkage = TaskLinkage(task_id=t2.task_id, time_scope_id=scope_id)
        linkage.created_at = datetime.now()

        # Append "roll => XX.Y" resolution to older linkages
        if new_linkages:
            new_linkages[-1].resolution = f"roll => {linkage.time_scope_id}"

        session.add(linkage)
        new_linkages.append(linkage)

    # For the first linkage, set the entire Task JSON
    new_linkages[0].detailed_resolution = pformat(t1.as_json())
    # For the final linkage, inherit any/all Task_v1 fields
    new_linkages[-1].resolution = t1.resolution
    new_linkages[-1].time_elapsed = t1.time_actual

    return t2


def _migrate_shallow_tree(session, t1: Task_v1) -> Task_v2:
    t2 = _migrate_simple(session, t1)

    new_linkages = []
    for scope_id in _get_scopes(t1):
        linkage = TaskLinkage(task_id=t2.task_id, time_scope_id=scope_id)
        linkage.created_at = datetime.now()

        # Append "roll => XX.Y" resolution to older linkages
        if new_linkages:
            new_linkages[-1].resolution = f"roll => {linkage.time_scope_id}"

        session.add(linkage)
        new_linkages.append(linkage)

    # For the first linkage, set the entire Task JSON
    new_linkages[0].detailed_resolution = pformat(t1.as_json())
    # For the final linkage, inherit any/all Task_v1 fields
    new_linkages[-1].resolution = t1.resolution
    new_linkages[-1].time_elapsed = t1.time_actual

    return t2


def _migrate_tree(session, t1: Task_v1) -> Task_v2:
    return _migrate_shallow_tree(session, t1)


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

    # DEBUG: this is not implemented well or correctly
    if t1.children:
        return None

    t2 = _do_one(tasks_v2_session, t1)

    try:
        tasks_v2_session.commit()
    except StatementError as e:
        tasks_v2_session.rollback()
        print(f"ERROR: Hit exception while parsing {t1}, skipping")
        print()
        print(e)
        print()
        pprint(t1.as_json())
        return None
    except IntegrityError as e:
        session.rollback()
        print(f"ERROR: Hit exception while parsing {t1}, skipping")
        print()
        print(e)
        print()
        pprint(t1.as_json())
        return None

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
