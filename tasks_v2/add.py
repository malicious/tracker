from sqlalchemy.exc import StatementError

from tasks.models import Task as Task_v1, TaskTimeScope
from tasks.time_scope import TimeScope
from tasks_v2.models import Task as Task_v2, TaskLinkage


def _migrate_childed_task(session, t1: Task_v1):
    """
    Returns new parent task, plus count of total migrated tasks
    """
    def print_task_and_children(depth, t: Task_v1):
        """
        Recursive print. Also counts the number of prints.
        """
        print("  " * depth + f"- #{t.task_id}: {t.desc}")
        task_count = 1

        for child in t.get_children():
            task_count += print_task_and_children(depth + 1, child)

        return task_count

    print(f"importing #{t1.task_id}, outline:")
    task_v1_count = print_task_and_children(0, t1)

    print("- TODO: not implemented")
    return None, 0


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
    new_t2 = Task_v2(desc=t1.desc, category=t1.category, created_at=t1.created_at, time_estimate=t1.time_estimate)

    # Check for a pre-existing task before creating one
    t2 = session.query(Task_v2) \
        .filter_by(desc=new_t2.desc, created_at=new_t2.created_at) \
        .one_or_none()
    if not t2:
        session.add(new_t2)
        t2 = new_t2
    else:
        print("- task already exists, updating columns instead")
        t2.category = new_t2.category

    try:
        session.commit()
    except StatementError as e:
        print("Hit exception when parsing:")
        print(t1.as_json())
        session.rollback()
        return None

    # And linkages
    t1_linkages = session.query(TaskTimeScope) \
        .filter_by(task_id=t1.task_id) \
        .all()
    if not t1_linkages:
        print(f"- no TaskTimeScope found for #{tts.task_id}, this should be impossible")
        print(f"- Task.first_scope is {t1.first_scope}")
        return None

    t1_scopes = [tts.time_scope_id for tts in t1_linkages]
    if t1.first_scope not in t1_scopes:
        print(f"- non-matching TaskTimeScope found for #{t1.task_id}: {t1.first_scope} not in {t1_scopes}")
        return None

    if len(t1_scopes) == 1:
        print(f"- TimeScope: {t1.first_scope} is \"{t1.resolution}\"")
        tl = TaskLinkage(task_id=t2.task_id, time_scope_id=t1.first_scope)
        tl.created_at = None
        tl.resolution = t1.resolution
        tl.time_elapsed = t1.time_actual
        session.add(tl)
    else:
        for ts in t1_scopes:
            tl = TaskLinkage(task_id=t2.task_id, time_scope_id=ts)
            print(f"- TimeScope: {ts} is \"{t1.resolution}\"")
            session.add(tl)

    return t2


def migrate_tasks(session, delete_current: bool = True):
    # Clear any Task_v2's from the existing db
    if delete_current:
        session.query(TaskLinkage).delete()
        session.query(Task_v2).delete()
        session.commit()

    # Helper functions for printing output
    MIGRATION_BATCH_SIZE = 10

    def print_header(next_task_id):
        print("=" * 72)
        print(f"Migrating up to {MIGRATION_BATCH_SIZE} tasks, starting with #{next_task_id}")
        print("=" * 72)
        print()

    def end_of_batch(count_total, count_success):
        input(f"Migrated {count_total} tasks ({count_success} successfully), press enter to continue migrating")
        print()
        print()

    # For every single task... migrate it
    count_total = len(Task_v1.query.all())
    count_success = 0

    for idx, t1 in enumerate(Task_v1.query.all()):
        if idx % MIGRATION_BATCH_SIZE == 0:
            print_header(t1.task_id)

        # Check for parents and children
        if t1.parent_id:
            print(f"skipping #{t1.task_id}: has a parent_id ({t1.parent_id})")
        elif t1.get_children():
            t2, count_migrated = _migrate_childed_task(session, t1)
            count_success += count_migrated
        else:
            t2 = _migrate_task(session, t1)
            if t2:
                count_success += 1

        print()
        if (idx+1) % MIGRATION_BATCH_SIZE == 0:
            end_of_batch(idx+1, count_success)

    # Evaluate success-ness
    if count_total == count_success:
        print("Successfully migrated all tasks.")
        print()
    else:
        print(f"FAIL: Only migrated {count_success} of {count_total} tasks")
        print()
