from datetime import date, datetime

import pytest

from tasks.database_models import Task, TaskLinkage


def test_task_constructor():
    t = Task(desc="test task for test_task_constructor")
    assert t


def test_create_and_commit(tasks_db):
    t = Task(desc="test task for committing to db")
    assert t.task_id is None

    tasks_db.add(t)
    tasks_db.commit()
    assert t.task_id is not None


def test_create_task_only(tasks_db):
    t = Task(desc="task with all attributes")
    t.category = "category theory for me"
    t.time_estimate = 4.200

    tasks_db.add(t)
    tasks_db.commit()
    assert t.task_id is not None


def test_create_and_retrieve(tasks_db):
    t = Task(desc="task for retrieval")
    tasks_db.add(t)
    tasks_db.commit()

    existing_task = Task.query \
        .filter_by(task_id=t.task_id) \
        .one()
    assert existing_task.task_id == t.task_id


def test_create_basic(tasks_db):
    t = Task(desc="basic task")
    tasks_db.add(t)
    tasks_db.flush()

    tl = TaskLinkage(
        task_id=t.task_id,
        import_source=t.import_source,
        time_scope=date(2021, 5, 23),
    )
    tl.created_at = datetime.now()
    tasks_db.add(tl)
    tasks_db.commit()


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


def test_linkage_at(tasks_db):
    t = Task(desc="g2ruI9wLN1A3cCJ6vLHI63gN")
    tasks_db.add(t)
    tasks_db.flush()

    tl_2 = t.linkage_at("2021-ww34.2")
    tl_2.resolution = "done, but check me for duplicates"
    tasks_db.add(tl_2)
    tasks_db.commit()

    tl_2b = t.linkage_at("2021-ww34.2")
    # TODO: Implement proper '==' on TaskLinkage
    assert tl_2b
    assert tl_2.task_id == tl_2b.task_id
    assert tl_2.time_scope == tl_2b.time_scope
    assert tl_2.resolution == tl_2b.resolution

    tl_3 = t.linkage_at("2021-ww34.3")
    assert tl_3
