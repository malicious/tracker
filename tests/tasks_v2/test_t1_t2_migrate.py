import io

from tasks_v1.add import import_from_csv
from tasks_v1.models import Task as Task_v1
from tasks_v2.migrate import migrate_tasks
from tasks_v2.models import Task as Task_v2


def test_migrate_one(task_v1_session, task_v2_session):
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
