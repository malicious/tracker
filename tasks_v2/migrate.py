from datetime import datetime
import json

from sqlalchemy.exc import IntegrityError, StatementError

from tasks_v1.models import Task as Task_v1, TaskTimeScope
from tasks_v1.time_scope import TimeScope, TimeScopeUtils
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
            raise ValueError(f"ERROR: Task #{t1.task_id} has child #{child_task.task_id} still open, must be resolved manually")

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
        for child in t1.get_children():
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
            if not tl.detailed_resolution:
                tl.detailed_resolution = json.dumps(t1.to_json_dict(), indent=4)

        # add "migrated from" note, where applicable
        if not tl.detailed_resolution:
            tl.detailed_resolution = f"migrated from Task_v1 #{t1.task_id}"
    del index, scope, tl

    # Sometimes child tasks have scopes that extend out past the parent
    final_linkage = draft_linkages_sorted[-1][1]
    if t1.resolution and not final_linkage.resolution:
            print(f"WARN: task #{t1.task_id} imported, but final child scope {final_linkage.time_scope_id} is later than final parent scope {t1.first_scope}")
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

        for child in t.get_children():
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


def migrate_tasks(tasks_v1_session,
                  tasks_v2_session,
                  delete_current: bool = True,
                  print_successes: bool = True):
    # Clear any Task_v2's from the existing db
    if delete_current:
        tasks_v2_session.query(TaskLinkage).delete()
        tasks_v2_session.query(Task_v2).delete()
        tasks_v2_session.commit()

    # Helper functions for printing output
    def print_batch_start(next_task_id):
        print("=" * 72)
        print(f"Migrating up to {MIGRATION_BATCH_SIZE} tasks (reverse order, starting at #{next_task_id})")
        print("=" * 72)
        print()

    def print_batch_end(count_total, count_success):
        print(f"Migrated {count_total} tasks ({count_success} completed successfully)")
        if count_success > count_total:
            print("(Childed tasks are migrated with the parent, so success count may be larger)")
        print()
        print()

    # For every single task... migrate it
    v1_tasks_query = tasks_v1_session.query(Task_v1)
    v1_tasks = v1_tasks_query \
        .order_by(Task_v1.task_id) \
        .all()

    count_total = len(v1_tasks)
    count_success = 0
    print(f"DEBUG: Found {count_total} Task_v1 to migrate")

    print_fn = lambda *args, **kwargs: None
    if print_successes:
        print_fn = print

    for idx, t1 in enumerate(v1_tasks):
        if idx % MIGRATION_BATCH_SIZE == 0:
            print_batch_start(t1.task_id)

        # Check for parents and children
        if t1.parent_id:
            print_fn(f"skipping #{t1.task_id}: will be migrated with parent (#{t1.parent_id})")
        else:
            t2, count_migrated = _migrate_one(tasks_v2_session, t1, print_fn)
            count_success += count_migrated

        print_fn()
        if (idx + 1) % MIGRATION_BATCH_SIZE == 0:
            print_batch_end(idx + 1, count_success)

    # Evaluate success-ness
    if count_total == count_success:
        print("Successfully migrated all tasks.")
        print()
    else:
        print(f"FAIL: Only migrated {count_success} of {count_total} tasks")
        print()
