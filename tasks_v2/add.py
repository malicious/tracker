from sqlalchemy.exc import StatementError

from tasks.models import Task as Task_v1, TaskTimeScope
from tasks_v2.models import Task as Task_v2, TaskLinkage

MIGRATION_BATCH_SIZE = 100


def _get_scopes(t: Task_v1):
    linkages = TaskTimeScope.query \
        .filter_by(task_id=t.task_id) \
        .order_by(TaskTimeScope.time_scope_id) \
        .all()
    return [tts.time_scope_id for tts in linkages]


def _migrate_task(session, t1: Task_v1):
    """
    Create and commit corresponding Task_v2 and TaskLinkage entries

    Expected to return None on failure, not raise exceptions
    """

    print(f"importing #{t1.task_id}: desc = {t1.desc}")
    if t1.parent_id:
        print("- has a parent task, skipping")
        return None

    # Create a new task that shares... enough
    t2 = Task_v2(desc=t1.desc, category=t1.category, created_at=t1.created_at, time_estimate=t1.time_estimate)
    try:
        session.add(t2)
        session.commit()
    except StatementError as e:
        print("Hit exception when parsing:")
        print(t1.to_json_dict())
        session.rollback()
        return None

    # And linkages (sorted, in case database was weird)
    t1_scopes = _get_scopes(t1)
    if not t1_scopes:
        print(f"- no TaskTimeScope found for #{t1.task_id}, this should be impossible")
        print(f"- Task.first_scope is {t1.first_scope}")
        return None

    if t1.first_scope not in t1_scopes:
        print(f"- non-matching TaskTimeScope found for #{t1.task_id}: {t1.first_scope} not in {t1_scopes}")
        return None

    final_scope = t1_scopes[-1]
    for idx, ts in enumerate(t1_scopes):
        # Handle the _last_ TimeScope specially, since it's the only one where "resolution" applies
        if ts == final_scope:
            tl = TaskLinkage(task_id=t2.task_id, time_scope_id=ts)
            tl.created_at = None
            tl.resolution = t1.resolution
            tl.time_elapsed = t1.time_actual
            print(f"- {tl.time_scope_id}: \"{tl.resolution}\"")
            session.add(tl)
        else:
            tl = TaskLinkage(task_id=t2.task_id, time_scope_id=ts)
            tl.resolution = f"roll => {t1_scopes[idx + 1]}"
            print(f"- {tl.time_scope_id}: \"{tl.resolution}\"")
            session.add(tl)

    return t2


def migrate_tasks(session, start_index, delete_current: bool = True, batch_size=MIGRATION_BATCH_SIZE):
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

    for idx, t1 in enumerate(v1_tasks):
        if idx % MIGRATION_BATCH_SIZE == 0:
            print_header(t1.task_id)

        # Check for parents and children
        if t1.parent_id:
            print(f"skipping #{t1.task_id}: will be migrated with parent (#{t1.parent_id})")
        elif t1.get_children():
            print(f"skipping #{t1.task_id}: tasks with children not supported yet")
        else:
            t2 = _migrate_task(session, t1)
            if t2:
                count_success += 1

        print()
        if (idx + 1) % MIGRATION_BATCH_SIZE == 0:
            end_of_batch(idx + 1, count_success)

    # Evaluate success-ness
    if count_total == count_success:
        print("Successfully migrated all tasks.")
        print()
    else:
        print(f"FAIL: Only migrated {count_success} of {count_total} tasks")
        print()
