from sqlalchemy.exc import StatementError
import pytest

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


def test_task_lacks_created_at():
    task = Task(desc="created_at test task")
    assert not hasattr(task, 'created_at')


def test_task_allow_duplicates(session):
    task_0 = Task(desc="test task 5A5CFA75-9372-4473-AB2C-48FBFE00A066 in 中文")
    session.add(task_0)

    task_1 = Task(desc="test task 5A5CFA75-9372-4473-AB2C-48FBFE00A066 in 中文")
    session.add(task_1)

    session.commit()


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


def test_linkage_disallow_duplicates(session):
    task = Task(desc="task 5")
    session.add(task)
    session.commit()

    linkage_0 = TaskLinkage(task_id=task.task_id, time_scope_id="2021-ww14.3")
    session.add(linkage_0)
    linkage_1 = TaskLinkage(task_id=task.task_id, time_scope_id="2021-ww14.3")
    session.add(linkage_1)

    with pytest.raises(StatementError):
        session.commit()


def test_empty_migration(session):
    migrate_tasks(session, start_index=None)
