import io

from tasks import _import_from_csv
from tracker import Task


def test_task_constructor():
    task = Task(desc="test task for test_task_constructor")
    assert task


def test_create_python(session):
    task = Task(desc="test task for database")
    assert task.task_id is None

    session.add(task)
    session.commit()
    assert task.task_id is not None


def test_dict_import():
    TEST_DESC = "sample descr x13212"
    TEST_CAT = "test cat 12453"

    csv_dict = {
        "desc": TEST_DESC,
        "category": TEST_CAT,
    }

    t = Task.from_csv(csv_dict)
    assert t.desc == TEST_DESC
    assert t.category == TEST_CAT
    assert t.created_at is None


def test_json_export():
    TEST_DESC = "sample descr aheou;lq"
    TEST_CATEGORY = "test cat g'l.',.p"

    json_dict = Task(desc = TEST_DESC, category = TEST_CATEGORY).to_json()

    assert json_dict['desc'] == TEST_DESC
    assert json_dict['category'] == TEST_CATEGORY
    assert 'created_at' not in json_dict


def test_csv_import(session):
    csv_test_file = """desc,
"csv test file desc",
"another one","""

    test_csv = io.StringIO(csv_test_file)
    _import_from_csv(test_csv, session)

    query = Task.query
    assert query.first()


def test_create_and_read_python(session):
    task = Task(desc="injected test task")
    session.add(task)
    session.commit()

    query = Task.query.filter_by(task_id=task.task_id)
    task_out = query.first()
    assert task_out.task_id == task.task_id


def test_create_app(test_app):
    pass


def test_create_and_read_app(test_app):
    pass


def test_create_rest(test_app):
    pass


def test_create_and_read_rest(test_app):
    pass
