from tasks_v1.models import Task, TaskTimeScope
from tasks_v1.time_scope import TimeScope


def test_task_constructor():
    task = Task(desc="test task for test_task_constructor",
                first_scope="2020-ww02.1")
    assert task


def test_create_python(task_v1_session):
    task = Task(desc="test task for database", first_scope="2020-ww02.2")
    assert task.task_id is None

    task_v1_session.add(task)
    task_v1_session.flush()
    assert task.task_id is not None


def test_create_quarterly(task_v1_session):
    task = Task(desc="아니아", first_scope="2020—Q4")
    time = TimeScope(task.first_scope)
    assert time.type == TimeScope.Type.quarter


def test_to_json_legacy():
    TEST_DESC = "sample descr aheou;lq"
    TEST_CATEGORY = "test cat g'l.',.p"
    TEST_SCOPE = "2011-ww38.3"

    t = Task(desc=TEST_DESC,
             category=TEST_CATEGORY,
             first_scope=TEST_SCOPE)
    json_dict = t.to_json_dict()

    assert json_dict['desc'] == TEST_DESC
    assert json_dict['category'] == TEST_CATEGORY
    assert json_dict['first_scope'] == TEST_SCOPE
    assert 'created_at' not in json_dict


def test_as_json(task_v1_session):
    TEST_DESC = "sample desc hchcoernn1 c"
    TEST_CATEGORY = "NqMxWNCBthIYp2e9aWrfeX8"
    TEST_SCOPE = "2021-ww24.5"

    t = Task(desc=TEST_DESC,
             category=TEST_CATEGORY,
             first_scope=TEST_SCOPE)
    task_v1_session.add(t)
    task_v1_session.flush()
    json_dict = t.as_json()

    assert json_dict['task_id']
    assert json_dict['desc'] == TEST_DESC
    assert json_dict['first_scope'] == TEST_SCOPE
    assert 'parent_id' not in json_dict


def test_create_and_read_python(task_v1_session):
    task = Task(desc="injected test task", first_scope="2016-ww27.4")
    task_v1_session.add(task)
    task_v1_session.commit()

    query = Task.query.filter_by(task_id=task.task_id)
    task_out = query.one()
    assert task_out.task_id == task.task_id


def test_orphan_properties(task_v1_session):
    task = Task(desc="orphan", first_scope="2021-ww24.5")
    task_v1_session.add(task)
    task_v1_session.commit()

    assert not task.parent
    assert not task.children

    json_dict = task.as_json(include_parents=True, include_children=True)
    assert 'parent_id' not in json_dict
    assert 'children' not in json_dict


def test_two_generation_properties(task_v1_session):
    parent_task = Task(desc="parent",
                       first_scope="2021-ww24.5")
    task_v1_session.add(parent_task)
    task_v1_session.flush()

    child_task = Task(desc="child",
                      first_scope="2021-ww24.6")
    child_task.parent_id = parent_task.task_id
    task_v1_session.add(child_task)
    task_v1_session.commit()

    assert not parent_task.parent
    assert parent_task.children == [child_task]

    assert child_task.parent == parent_task
    assert not child_task.children


def test_2g_sqlalchemy_relationships(task_v1_session):
    parent_task = Task(desc="parent",
                       first_scope="2021-ww24.5")
    task_v1_session.add(parent_task)
    task_v1_session.flush()

    child_task = Task(desc="child",
                      first_scope="2021-ww24.6")
    child_task.parent_id = parent_task.task_id
    task_v1_session.add(child_task)
    task_v1_session.commit()

    bystander = Task(desc="completely unrelated task",
                     first_scope="2021-ww02.1")
    task_v1_session.add(bystander)

    bystander2 = Task(desc="totally unrelated task",
                      first_scope="2021-ww03.1")
    task_v1_session.add(bystander2)
    task_v1_session.commit()

    assert not parent_task.parent
    assert parent_task.children == [child_task]

    assert child_task.parent == parent_task
    assert not child_task.children


def test_one_scope(task_v1_session):
    t = Task(desc="aoetuhnano",
             first_scope="2000-ww22.2")
    task_v1_session.add(t)
    task_v1_session.flush()

    tts = TaskTimeScope(task_id=t.task_id, time_scope_id=t.first_scope)
    task_v1_session.add(tts)
    task_v1_session.commit()

    assert len(t.scopes) == 1
    assert t.scopes[0] == tts
    assert tts.task == t


def test_multi_scope(task_v1_session):
    t = Task(desc="hhhhhhhhhh",
             first_scope="2020-ww20.1")
    task_v1_session.add(t)
    task_v1_session.flush()

    task_v1_session.add(TaskTimeScope(task_id=t.task_id, time_scope_id=t.first_scope))
    task_v1_session.add(TaskTimeScope(task_id=t.task_id, time_scope_id="2020-ww20.2"))
    task_v1_session.add(TaskTimeScope(task_id=t.task_id, time_scope_id="2020-ww20.3"))
    task_v1_session.add(TaskTimeScope(task_id=t.task_id, time_scope_id="2020-ww20.4"))
    task_v1_session.add(TaskTimeScope(task_id=t.task_id, time_scope_id="2020-ww20.5"))
    task_v1_session.commit()

    assert len(t.scopes) == 5
    assert t.scopes[0]
