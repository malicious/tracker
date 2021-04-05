from tasks_v2.add import migrate_tasks
from tasks_v2.models import Task, TaskLinkage


def test_task_constructor():
    task = Task(desc="test task")
    assert task


def test_task_create(session):
    task = Task(desc="task 3")
    assert task.task_id is None

    session.add(task)
    session.commit()
    assert task.task_id


def test_linkage_constructor():
    task = Task(desc="task 2")
    linkage = TaskLinkage(task_id=task.task_id)

    assert linkage


def test_linkage_create(session):
    task = Task(desc="task 4")
    session.add(task)
    session.commit()

    linkage = TaskLinkage(task_id=task.task_id, time_scope_id="2021-ww11.6")
    session.add(linkage)
    session.commit()

    assert linkage.task_id


def test_empty_migration(session):
    migrate_tasks(session, start_index=None)
