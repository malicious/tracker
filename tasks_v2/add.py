from sqlalchemy.exc import StatementError

from tasks.models import Task as Task_v1, TaskTimeScope
from tasks.time_scope import TimeScope
from tasks_v2.models import Task as Task_v2, TaskLinkage


def _migrate_parented_task():
    pass


def _migrate_task(session, t1: Task_v1):
    print(f"importing: desc = {t1.desc}")

    # Create a new task that shares... enough
    new_t2 = Task_v2(desc=t1.desc, category=t1.category, created_at=t1.created_at, time_estimate=t1.time_estimate)
    # TODO: Figure out what to do with parent_id fields
    if t1.parent_id:
        print("- task has a parent_id, skipping")
        return None

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
        raise ValueError

    t1_scopes = [tts.time_scope_id for tts in t1_linkages]
    if t1.first_scope not in t1_scopes:
        print(f"- non-matching TaskTimeScope found for #{t1.task_id}: {t1.first_scope} not in {t1_scopes}")
        raise ValueError

    if len(t1_scopes) == 1:
        print(f"- TimeScope: {t1.first_scope} is \"{t1.resolution}\"")
        tl = TaskLinkage(task_id=t2.task_id, time_scope_id=t1.first_scope)
        tl.created_at = None
        tl.resolution = t1.resolution
        tl.time_elapsed = t1.time_actual
        session.add(tl)

    for ts in t1_scopes:
        tl = TaskLinkage(task_id=t2.task_id, time_scope_id=ts)
        print(f"- TimeScope: {ts} is \"{t1.resolution}\"")

    return t2


def migrate_tasks(session, delete_current: bool = True):
    # Clear any Task_v2's from the existing db
    if delete_current:
        session.query(TaskLinkage).delete()
        session.query(Task_v2).delete()
        session.commit()

    # Helper functions for printing output
    MIGRATION_BATCH_SIZE = 5

    def print_header(next_task_id):
        print("=" * 72)
        print(f"Migrating up to {MIGRATION_BATCH_SIZE} tasks, starting with #{next_task_id}")
        print("=" * 72)
        print()

    def end_of_batch(done_total, done_successfully):
        input(f"Migrated {done_total} tasks ({done_successfully} successfully), press enter to continue migrating")
        print()
        print()

    # For every single task... migrate it
    successful_migrations = 0

    for idx, t1 in enumerate(Task_v1.query.all()):
        if idx % MIGRATION_BATCH_SIZE == 0:
            print_header(t1.task_id)

        t2 = _migrate_task(session, t1)
        if t2:
            successful_migrations += 1

        print()
        if (idx+1) % MIGRATION_BATCH_SIZE == 0:
            end_of_batch(idx+1, successful_migrations)

    print(f"Completed migration of {successful_migrations}/{len(Task_v1.query.all())} tasks")
