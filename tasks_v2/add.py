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


def _migrate_childed_task(session, t1: Task_v1, print_fn):
    """
    Returns new parent task, plus count of total migrated tasks
    """
    def print_task_and_children(depth, t: Task_v1):
        """
        Recursive print. Also counts the number of prints.
        """
        print_fn("  " * depth + f"- #{t.task_id}: ({t.resolution}) {t.desc}")
        print_fn("  " * depth + f"  scopes: {_get_scopes(t)}")
        task_count = 1

        for child in t.get_children():
            task_count += print_task_and_children(depth + 1, child)

        return task_count

    print_fn(f"importing #{t1.task_id}, outline:")
    print_fn()
    task_v1_count = print_task_and_children(0, t1)
    print_fn()

    # Start actual migration
    t2 = Task_v2(desc=t1.desc, category=t1.category, created_at=t1.created_at, time_estimate=t1.time_estimate)
    try:
        session.add(t2)
        session.commit()
    except StatementError as e:
        print("Hit exception when parsing:")
        print(t1.as_json())
        session.rollback()
        return None

    # TODO: de-duplicate this code with _migrate_task()
    draft_linkages = {}

    # Generate linkages for parent task
    t1_scopes = _get_scopes(t1)
    for index, scope in enumerate(t1_scopes):
        tl = TaskLinkage(task_id=t2.task_id, time_scope_id=scope)
        if scope == t1_scopes[-1]:
            tl.resolution = t1.resolution
            tl.time_elapsed = t1.time_actual
        draft_linkages[scope] = tl

    # Simple case: one child, which is an info type
    t1_children = t1.get_children()
    if len(t1_children) == 1 and t1.resolution == "info":
        if t1_scopes != _get_scopes(t1_children[0]):
            print("- get fukt")
            return None, 0
        else:
            draft_linkages[t1_scopes[0]].detailed_resolution = t1_children[0].desc

    for child in t1.get_children():
        child_scopes = _get_scopes(child)
        for index, scope in enumerate(child_scopes):
            if not scope in draft_linkages:
                tl = TaskLinkage(task_id=t2.task_id, time_scope_id=scope)
                tl.detailed_resolution = child.desc
                tl.time_elapsed = child.time_actual
                draft_linkages[scope] = tl
            else:
                tl.detailed_resolution = child.desc

    # plan:
    # - import the parent task "normally"
    # - for each child task:
    #   - if the child task is unresolved, just do the link-in-text
    #     - looks like there's only two options: link-in-text, or append to resolution
    #   - if there's only one scope, add it as a linkage
    #     - if the linkage already exists (which it should), append it to detailed_resolution
    #       (with created_at formatted into markdown comment)
    #   - if there's multiple scopes...
    #     - deserves to be its own high-level task, link in text (" (child of #XXX)")
    #       - which implies that "#%d" is an explicitly understood string, and we gotta check for it now
    # - for things that were unclear, print and prompt for review

    for scope, tl in sorted(draft_linkages.items()):
        print_fn(f"- {tl.time_scope_id}: \"{tl.resolution}\" / {tl.detailed_resolution}")
        session.add(tl)
    session.commit()

    print("- TODO: not implemented,  press enter to continue")
    input()
    print()
    return None, 0


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
            t2, count_migrated = _migrate_childed_task(session, t1, print)
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
