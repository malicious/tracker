import io

from tasks_v1.add import import_from_csv
from tasks_v1.models import Task as Task_v1, TaskTimeScope
from tasks_v2.migrate import _migrate_one, migrate_tasks
from tasks_v2.models import Task as Task_v2


def test_migrate_zero(task_v1_session, task_v2_session):
    migrate_tasks(task_v1_session, task_v2_session)


def test_migrate_arbitrary(task_v1_session, task_v2_session):
    csv_test_file = """desc,scopes
"csv test file desc",2020-ww12.1 2019-ww14.5
"another one",2020-ww34
"another one",2020-ww52.4"""

    test_csv = io.StringIO(csv_test_file)
    import_from_csv(test_csv, task_v1_session)

    query = Task_v1.query
    assert query.first()

    migrate_tasks(task_v1_session, task_v2_session)

    q2 = Task_v2.query
    assert q2.first()


def test_simple_one(task_v1_session, task_v2_session):
    t1 = Task_v1(desc="here is a very basic task")
    t1.first_scope = "2021-ww24.1"
    t1.resolution = "skipped, didn't care for it"
    task_v1_session.add(t1)
    task_v1_session.flush()

    tts = TaskTimeScope(task_id=t1.task_id, time_scope_id=t1.first_scope)
    task_v1_session.add(tts)
    task_v1_session.commit()

    _migrate_one(task_v2_session, t1, print)
    q2 = Task_v2.query.first()
    assert q2.desc == "here is a very basic task"
