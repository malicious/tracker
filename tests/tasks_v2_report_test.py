import itertools

from tasks.time_scope import TimeScope
from tasks_v2.models import Task, TaskLinkage
from tasks_v2.report import generate_tasks_by_scope, report_one_task


def test_report_one_empty():
    json_dict = report_one_task(110249)

    assert json_dict
    assert "error" in json_dict


def test_report_one_simple(session):
    t2 = Task(desc="test task")
    session.add(t2)
    session.commit()

    json_dict = report_one_task(t2.task_id)
    assert json_dict
    assert "task_id" in json_dict
    assert json_dict["task_id"] == t2.task_id


def test_report_empty():
    tasks_by_scope = generate_tasks_by_scope(page_scope=None)

    assert tasks_by_scope is not None
    assert not tasks_by_scope


def test_report_simple(session):
    t2 = Task(desc="reported task test")
    session.add(t2)
    session.commit()

    TEST_SCOPE = "2021-ww14.1"
    tl = TaskLinkage(task_id=t2.task_id, time_scope_id=TEST_SCOPE)
    session.add(tl)

    tasks_by_scope = generate_tasks_by_scope(page_scope=None)
    assert tasks_by_scope
    assert TEST_SCOPE in tasks_by_scope
    assert len(tasks_by_scope[TEST_SCOPE]) == 1


def test_report_simple_2(session):
    t2 = Task(desc="reported task test (multi-scope)")
    session.add(t2)
    session.commit()

    TEST_SCOPE_MONDAY = "2021-ww14.1"
    tl_monday = TaskLinkage(task_id=t2.task_id, time_scope_id=TEST_SCOPE_MONDAY)
    session.add(tl_monday)

    TEST_SCOPE_TUESDAY = "2021-ww14.2"
    tl_tuesday = TaskLinkage(task_id=t2.task_id, time_scope_id=TEST_SCOPE_TUESDAY)
    session.add(tl_tuesday)

    session.commit()

    tasks_by_scope = generate_tasks_by_scope(page_scope=None)
    assert len(tasks_by_scope.items()) == 2

    assert TEST_SCOPE_MONDAY in tasks_by_scope
    assert len(tasks_by_scope[TEST_SCOPE_MONDAY]) == 1
    assert TEST_SCOPE_TUESDAY in tasks_by_scope
    assert len(tasks_by_scope[TEST_SCOPE_TUESDAY]) == 1


def test_report_week(session):
    t2 = Task(desc="reported task test (multi-scope)")
    session.add(t2)
    session.commit()

    TEST_SCOPE_MONDAY = "2021-ww14.1"
    tl_monday = TaskLinkage(task_id=t2.task_id, time_scope_id=TEST_SCOPE_MONDAY)
    session.add(tl_monday)

    TEST_SCOPE_TUESDAY = "2021-ww14.2"
    tl_tuesday = TaskLinkage(task_id=t2.task_id, time_scope_id=TEST_SCOPE_TUESDAY)
    session.add(tl_tuesday)

    session.commit()

    # Same task will show up in multiple scopes
    tasks_by_scope = generate_tasks_by_scope(page_scope=TimeScope("2021-ww14"))

    flatten_unique = lambda x: set(itertools.chain.from_iterable(x))
    assert len(flatten_unique(tasks_by_scope.values())) == 1
