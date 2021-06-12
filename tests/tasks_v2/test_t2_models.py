from datetime import date

import pytest

from tasks_v2 import Task
from tasks_v2.models import TaskLinkage


def test_task_constructor():
    t = Task(desc="test task for test_task_constructor")
    assert t


def test_create_and_commit(task_v2_session):
    t = Task(desc="test task for committing to db")
    assert t.task_id is None

    task_v2_session.add(t)
    task_v2_session.commit()
    assert t.task_id is not None


def test_create_task_only(task_v2_session):
    t = Task(desc="task with all attributes")
    t.category = "category theory for me"
    t.time_estimate = 4.200

    task_v2_session.add(t)
    task_v2_session.commit()
    assert t.task_id is not None


def test_create_and_retrieve(task_v2_session):
    t = Task(desc="task for retrieval")
    task_v2_session.add(t)
    task_v2_session.commit()

    existing_task = Task.query \
        .filter_by(task_id=t.task_id) \
        .one()
    assert existing_task.task_id == t.task_id


def test_create_basic(task_v2_session):
    t = Task(desc="basic task")
    task_v2_session.add(t)
    task_v2_session.commit()

    tl = TaskLinkage(task_id=t.task_id, time_scope=date(2021, 5, 23))
    task_v2_session.add(tl)
    task_v2_session.commit()


def test_tl_ts_set():
    tl = TaskLinkage()
    tl.time_scope_id = "2021-ww23.6"
    assert tl.time_scope.year == 2021
    assert tl.time_scope.month == 6
    assert tl.time_scope.day == 12


def test_tl_ts_get():
    tl = TaskLinkage()
    tl.time_scope = date(2021, 6, 12)
    assert tl.time_scope_id == "2021-ww23.6"


def test_tl_ts_set_invalid():
    tl = TaskLinkage()
    with pytest.raises(ValueError):
        tl.time_scope_id = "garbage"
