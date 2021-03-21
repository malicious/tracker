from sqlalchemy.exc import StatementError

from tasks.models import Task as Task_v1
from tasks_v2.models import Task as Task_v2


def migrate_task(session, t1: Task_v1):
    # Create a new task that shares... enough
    new_t2 = Task_v2(desc=t1.desc, category=t1.category, created_at=t1.created_at, time_estimate=t1.time_estimate)

    # Check for a pre-existing task before creating one
    t2 = Task_v2.query \
        .filter_by(desc=new_t2.desc, created_at=new_t2.created_at) \
        .one_or_none()
    if not t2:
        session.add(t2)
        t2 = new_t2
    else:
        t2.category = new_t2.category

    try:
        session.commit()
    except StatementError as e:
        print("Hit exception when parsing:")
        print(t1.as_json())
        session.rollback()
        raise

    # TODO: Figure out what to do with parent_id fields


def migrate_tasks(session):
    # TODO: First, clear any Task_v2's from the existing db

    # For every single task... migrate it
    for t1 in Task_v1.query.all():
        try:
            migrate_task(session, t1)
        except StatementError:
            continue

    print(f"Completed migration of {len(Task_v1.query.all())} tasks")
