from tasks_v1.models import Task as Task_v1
from tasks_v2.models import Task as Task_v2, TaskLinkage

MIGRATION_BATCH_SIZE = 50


def _migrate_one(session, t1: Task_v1, print_fn):
    print_fn(f"skipping {t1}")
    return None, 0


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
