from tasks_v1.models import Task
from tasks_v1.time_scope import TimeScope


def test_task_constructor():
    task = Task(desc="test task for test_task_constructor", first_scope="2020-ww02.1")
    assert task


def test_create_python(task_v1_session):
    task = Task(desc="test task for database", first_scope="2020-ww02.2")
    assert task.task_id is None

    task_v1_session.add(task)
    task_v1_session.commit()
    assert task.task_id is not None


def test_create_quarterly(task_v1_session):
    task = Task(desc="아니아", first_scope="2020—Q4")
    time = TimeScope(task.first_scope)
    assert time.type == TimeScope.Type.quarter


def test_json_export():
    TEST_DESC = "sample descr aheou;lq"
    TEST_CATEGORY = "test cat g'l.',.p"
    TEST_SCOPE = "2011-ww38.3"

    json_dict = Task(desc=TEST_DESC,
                     category=TEST_CATEGORY,
                     first_scope=TEST_SCOPE).to_json_dict()

    assert json_dict['desc'] == TEST_DESC
    assert json_dict['category'] == TEST_CATEGORY
    assert json_dict['first_scope'] == TEST_SCOPE
    assert 'created_at' not in json_dict


def test_create_and_read_python(task_v1_session):
    task = Task(desc="injected test task", first_scope="2016-ww27.4")
    task_v1_session.add(task)
    task_v1_session.commit()

    query = Task.query.filter_by(task_id=task.task_id)
    task_out = query.one()
    assert task_out.task_id == task.task_id
