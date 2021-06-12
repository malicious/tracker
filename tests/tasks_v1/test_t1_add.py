import io

import tasks_v1
from tasks_v1.add import import_from_csv
from tasks_v1.models import Task
from tasks_v1.report import matching_scopes, latest_scope
from tasks_v1.time_scope import TimeScope


def test_dict_import():
    TEST_DESC = "sample descr x13212"
    TEST_CAT = "test cat 12453"
    TEST_SCOPE = "2020-ww04.4"

    csv_entry = {
        "desc": TEST_DESC,
        "category": TEST_CAT,
        "first_scope": TEST_SCOPE,
    }

    t = tasks_v1.add.from_csv(csv_entry)
    assert t.desc == TEST_DESC
    assert t.category == TEST_CAT
    assert t.first_scope == TEST_SCOPE
    assert t.created_at is None


def test_csv_import(task_v1_session):
    csv_test_file = """desc,scopes
"csv test file desc",2020-ww12.1 2019-ww14.5
"another one",2020-ww34
"another one",2020-ww52.4"""

    test_csv = io.StringIO(csv_test_file)
    import_from_csv(test_csv, task_v1_session)

    query = Task.query
    assert query.first()


def test_csv_ordering(task_v1_session):
    csv_test_file = """desc,scopes
"csv test file desc",2020-ww12.1 2019-ww14.5"""

    import_from_csv(io.StringIO(csv_test_file), task_v1_session)

    t: Task = Task.query.one()
    assert t.first_scope == "2019-ww14.5"


def test_max_import_depth(task_v1_session):
    csv_test_file = """id,parent_id,desc,scopes
1,,task 1,2020-ww39.1
2,1,task 2,2020-ww39.1
3,2,task 3,2020-ww39.1
4,3,task 4,2020-ww39.1
5,4,task 5,2020-ww39.1
6,5,task 6,2020-ww39.1
"""

    import_from_csv(io.StringIO(csv_test_file), task_v1_session)

    query = Task.query.all()
    assert len(query) == 5


def test_update_task(task_v1_session):
    csv_orig = """id,parent_id,desc,scopes
1,,task 1,2020-ww39.1
"""
    csv_updated = """id,parent_id,desc,scopes,resolution
1,,task 1,2020-ww39.1 2020-ww41.1,done
"""

    import_from_csv(io.StringIO(csv_orig), task_v1_session)
    import_from_csv(io.StringIO(csv_updated), task_v1_session)

    query = Task.query.all()
    assert len(query) == 1
    assert query[0].resolution == "done"


def test_latest_scope(task_v1_session):
    csv_test_file = """desc,scopes
task 1,2020-ww39.1 2020-ww39.2 2020-ww39.3
"""

    import_from_csv(io.StringIO(csv_test_file), task_v1_session)
    t: Task = Task.query.all()[0]

    assert len(list(matching_scopes(t.task_id))) == 3
    assert latest_scope(t.task_id, TimeScope("2020-ww39.1")) == "2020-ww39.3"
    assert not latest_scope(t.task_id, TimeScope("2020-ww39.3"))
