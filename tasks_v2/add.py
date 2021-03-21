from tasks.models import Task as Task_v1
from tasks_v2.models import Task as Task_v2


def migrate(session, t1: Task_v1):
    # Create a new task that shares... enough
    t2 = Task_v2(desc=t1.desc, category=t1.category, created_at=t1.created_at, time_estimate=t1.time_estimate)
    session.add(t2)
    session.commit()


def migrate(session):
    # TODO: First, clear any Task_v2's from the existing db

    # For every single task... migrate it
    for t1 in Task_v1.query.all():
        migrate(session, t1)

    print(f"Completed migration of {len(Task_v1.query.all())} tasks")
