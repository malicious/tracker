import io

import tasks
from tasks.add import import_from_csv
from tasks.models import Task
from tasks.time_scope import TimeScope


def test_task_constructor():
    task = Task(desc="test task for test_task_constructor", first_scope="2020-ww02.1")
    assert task


def test_create_python(session):
    task = Task(desc="test task for database", first_scope="2020-ww02.2")
    assert task.task_id is None

    session.add(task)
    session.commit()
    assert task.task_id is not None


def test_create_quarterly(session):
    task = Task(desc="아니아", first_scope="2020—Q4")
    time = TimeScope(task.first_scope)
    assert time.type == TimeScope.Type.quarter


def test_dict_import():
    TEST_DESC = "sample descr x13212"
    TEST_CAT = "test cat 12453"
    TEST_SCOPE = "2020-ww04.4"

    csv_entry = {
        "desc": TEST_DESC,
        "category": TEST_CAT,
        "first_scope": TEST_SCOPE,
    }

    t = tasks.add.from_csv(csv_entry)
    assert t.desc == TEST_DESC
    assert t.category == TEST_CAT
    assert t.first_scope == TEST_SCOPE
    assert t.created_at is None


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


def test_csv_import(session):
    csv_test_file = """desc,scopes
"csv test file desc",2020-ww12.1 2019-ww14.5
"another one",2020-ww34
"another one",2020-ww52.4"""

    test_csv = io.StringIO(csv_test_file)
    import_from_csv(test_csv, session)

    query = Task.query
    assert query.first()


def test_csv_ordering(session):
    csv_test_file = """desc,scopes
"csv test file desc",2020-ww12.1 2019-ww14.5"""

    import_from_csv(io.StringIO(csv_test_file), session)

    t: Task = Task.query.one()
    assert t.first_scope == "2019-ww14.5"


def test_create_and_read_python(session):
    task = Task(desc="injected test task", first_scope="2016-ww27.4")
    session.add(task)
    session.commit()

    query = Task.query.filter_by(task_id=task.task_id)
    task_out = query.one()
    assert task_out.task_id == task.task_id


def test_max_import_depth(session):
    csv_test_file = """id,parent_id,desc,scopes
1,,task 1,2020-ww39.1
2,1,task 2,2020-ww39.1
3,2,task 3,2020-ww39.1
4,3,task 4,2020-ww39.1
5,4,task 5,2020-ww39.1
6,5,task 6,2020-ww39.1
"""

    import_from_csv(io.StringIO(csv_test_file), session)

    query = Task.query.all()
    assert len(query) == 5


def test_update_task(session):
    csv_orig = """id,parent_id,desc,scopes
1,,task 1,2020-ww39.1
"""
    csv_updated = """id,parent_id,desc,scopes,resolution
1,,task 1,2020-ww39.1 2020-ww41.1,done
"""

    import_from_csv(io.StringIO(csv_orig), session)
    import_from_csv(io.StringIO(csv_updated), session)

    query = Task.query.all()
    assert len(query) == 1
    assert query[0].resolution == "done"
