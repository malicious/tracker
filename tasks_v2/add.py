from sqlalchemy.exc import StatementError

from tasks.models import Task as Task_v1, TaskTimeScope
from tasks.time_scope import TimeScope
from tasks_v2.models import Task as Task_v2, TaskLinkage


MIGRATION_BATCH_SIZE = 1000


def _get_scopes(t: Task_v1):
    linkages = TaskTimeScope.query \
        .filter_by(task_id=t.task_id) \
        .order_by(TaskTimeScope.time_scope_id) \
        .all()
    return [tts.time_scope_id for tts in linkages]


def _construct_linkages(t1: Task_v1, t2: Task_v2):
    """
    Turn TaskTimeScopes and child tasks into TaskLinkages

    - TODO: de-duplicate this code with _migrate_task()
    - TODO: created_at times could get imported, too
    """
    t1_children = t1.get_children()
    draft_linkages = {}

    # Add all scopes attached to Task_v1
    t1_scopes = _get_scopes(t1)
    for index, scope in enumerate(t1_scopes):
        tl = TaskLinkage(task_id=t2.task_id, time_scope_id=scope)
        draft_linkages[scope] = tl

        # Put resolution info into final scope
        if scope == t1_scopes[-1]:
            tl.resolution = t1.resolution
            tl.time_elapsed = t1.time_actual

        # DEBUG
        tl = None

    # Case: unclear, gonna do our best
    def parse_child(t1: Task_v1):
        for index, scope in enumerate(_get_scopes(t1)):
            # print(f"DEBUG: evaluating #{t1.task_id}, scope {scope}")

            # Create a new linkage if child scopes aren't a subset
            if not scope in draft_linkages:
                tl = TaskLinkage(task_id=t2.task_id, time_scope_id=scope)
                tl.time_elapsed = t1.time_actual
                draft_linkages[scope] = tl
                tl = None

            # Each child only gets to show up in its earliest scope
            if index == 0:
                # Generate info string for child task
                info_string = t1.desc
                if not t1.resolution:
                    raise ValueError(f"Child task #{t1.task_id} is still open, please handle this")
                if t1.resolution != "info":
                    info_string = f"({t1.resolution}) {t1.desc}"

                # Set or append the info string
                tl = draft_linkages[scope]

                if tl.detailed_resolution:
                    # print(f"DEBUG: appending detailed_resolution to scope {scope}")

                    # Multiple child tasks, append together
                    if tl.detailed_resolution[0:2] != "- ":
                        tl.detailed_resolution = f"- {tl.detailed_resolution}"
                    tl.detailed_resolution = f"{tl.detailed_resolution}\n- {info_string}"

                else:
                    # print(f"DEBUG: setting detailed_resolution for scope {scope}")
                    tl.detailed_resolution = info_string

    def add_child_tasks(t1: Task_v1):
        for child in t1.get_children():
            # print(f"DEBUG: evaluating child #{child.task_id}")
            parse_child(child)

            # Tail recursion here
            add_child_tasks(child)

    add_child_tasks(t1)

    # Done, attempt to set the initial scope as "created_at", if possible
    if not draft_linkages[t1.first_scope].resolution:
        draft_linkages[t1.first_scope].resolution = "created_at"

    # Done with import attempt, fill in "roll =>" entries
    draft_linkages_sorted = sorted(draft_linkages.items())
    for index, (scope, tl) in enumerate(draft_linkages_sorted):
        # Skip the last entry in the set
        if index == len(draft_linkages_sorted)-1:
            continue

        if not tl.resolution:
            tl.resolution = f"roll => {draft_linkages_sorted[index+1][0]}"

    # Sometimes child tasks have scopes that extend out past the parent
    if t1.resolution and not draft_linkages_sorted[-1][1].resolution:
        raise ValueError("Top-level resolution didn't propagate to final linkage")

    return draft_linkages



def _migrate_childed_task(session, t1: Task_v1, print_fn):
    """
    Returns new parent task, plus count of total migrated tasks
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

    # Construct Task_v2
    t2 = Task_v2(desc=t1.desc, category=t1.category, created_at=t1.created_at, time_estimate=t1.time_estimate)
    try:
        session.add(t2)
        session.commit()
    except StatementError as e:
        print("Hit exception when parsing:")
        print(t1.as_json())
        session.rollback()
        return None

    # Print Task_v2 info
    print_fn(f"imported to Task_v2:")
    print_fn("-" * 72)
    print_fn()

    print_fn(f"{t2.desc}")
    print_fn()

    try:
        t2_linkages = _construct_linkages(t1, t2)
    except ValueError as e:
        print(e)
        input(f"Import failed for task #{t1.task_id}, press enter to continue")
        return None, 0

    for scope, tl in sorted(t2_linkages.items()):
        print_fn(f"- {tl.time_scope_id}: {tl.resolution} / {tl.detailed_resolution}")
        session.add(tl)

    print_fn()
    print_fn()

    session.commit()
    return t2, task_v1_count


def _migrate_task(session, t1: Task_v1, print_fn):
    """
    Create and commit corresponding Task_v2 and TaskLinkage entries

    Expected to return None on failure, not raise exceptions
    """

    print_fn(f"importing #{t1.task_id}: desc = {t1.desc}")
    if t1.parent_id:
        print_fn("- has a parent task, skipping")
        return None

    # Create a new task that shares... enough
    t2 = Task_v2(desc=t1.desc, category=t1.category, created_at=t1.created_at, time_estimate=t1.time_estimate)
    try:
        session.add(t2)
        session.commit()
    except StatementError as e:
        print("Hit exception when parsing:")
        print(t1.as_json())
        session.rollback()
        return None

    # And linkages (sorted, in case database was weird)
    t1_scopes = _get_scopes(t1)
    if not t1_scopes:
        print_fn(f"- no TaskTimeScope found for #{tts.task_id}, this should be impossible")
        print_fn(f"- Task.first_scope is {t1.first_scope}")
        return None

    if t1.first_scope not in t1_scopes:
        print(f"- non-matching TaskTimeScope found for #{t1.task_id}: {t1.first_scope} not in {t1_scopes}")
        return None

    final_scope = t1_scopes[-1]
    for idx, ts in enumerate(t1_scopes):
        # TODO: Turn "Quarter" scopes into something more specific

        # Handle the _last_ TimeScope specially, since it's the only one where "resolution" applies
        if ts == final_scope:
            tl = TaskLinkage(task_id=t2.task_id, time_scope_id=ts)
            tl.created_at = None
            tl.resolution = t1.resolution
            tl.time_elapsed = t1.time_actual
            print_fn(f"- {tl.time_scope_id}: \"{tl.resolution}\"")
            session.add(tl)
        else:
            tl = TaskLinkage(task_id=t2.task_id, time_scope_id=ts)
            tl.resolution = f"roll => {t1_scopes[idx+1]}"
            print_fn(f"- {tl.time_scope_id}: \"{tl.resolution}\"")
            session.add(tl)

    return t2


def migrate_tasks(session, start_index, delete_current: bool = True, batch_size = MIGRATION_BATCH_SIZE, print_successful: bool = False):
    # Clear any Task_v2's from the existing db
    if delete_current:
        session.query(TaskLinkage).delete()
        session.query(Task_v2).delete()
        session.commit()

    # Helper functions for printing output
    def print_header(next_task_id):
        print("=" * 72)
        print(f"Migrating up to {MIGRATION_BATCH_SIZE} tasks (reverse order, starting at #{next_task_id})")
        print("=" * 72)
        print()

    def end_of_batch(count_total, count_success):
        print(f"Migrated {count_total} tasks ({count_success} completed successfully)")
        if count_success > count_total:
            print("(Childed tasks are migrated with the parent, so success count may be larger)")
        input("press enter to continue migrating")
        print()
        print()

    # For every single task... migrate it
    v1_tasks_query = session.query(Task_v1)
    if start_index:
        v1_tasks_query = v1_tasks_query.filter(Task_v1.task_id <= start_index)
    v1_tasks = v1_tasks_query \
        .order_by(Task_v1.task_id.desc()) \
        .all()

    count_total = len(v1_tasks)
    count_success = 0
    print_fn = lambda *args, **kwargs: None
    if print_successful:
        print_fn = print

    for idx, t1 in enumerate(v1_tasks):
        if idx % MIGRATION_BATCH_SIZE == 0:
            print_header(t1.task_id)

        # Check for parents and children
        if t1.parent_id:
            if print_successful:
                print(f"skipping #{t1.task_id}: will be migrated with parent (#{t1.parent_id})")
        elif t1.get_children():
            t2, count_migrated = _migrate_childed_task(session, t1, print_fn)
            count_success += count_migrated
        else:
            t2 = _migrate_task(session, t1, print_fn)
            if t2:
                count_success += 1

        print_fn()
        if (idx+1) % MIGRATION_BATCH_SIZE == 0:
            end_of_batch(idx+1, count_success)

    # Evaluate success-ness
    if count_total == count_success:
        print("Successfully migrated all tasks.")
        print()
    else:
        print(f"FAIL: Only migrated {count_success} of {count_total} tasks")
        print()
