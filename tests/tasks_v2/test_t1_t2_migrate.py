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
    t2 = Task_v2.query.first()
    assert t2.desc == "here is a very basic task"


def test_hundred_scopes(task_v1_session, task_v2_session):
    TDESC = "default task description help"

    t1 = Task_v1(desc=TDESC)
    t1.first_scope = "2011-ww11.1"
    task_v1_session.add(t1)
    task_v1_session.flush()

    for n in range(11, 49):
        new_scope = f"20{n}-ww{n}.1"
        tts = TaskTimeScope(task_id=t1.task_id, time_scope_id=new_scope)
        task_v1_session.add(tts)

    task_v1_session.commit()

    _migrate_one(task_v2_session, t1, print)
    t2 = Task_v2.query.one()
    assert t2.desc == TDESC
    assert len(t2.linkages) == 38


def test_duplicates_get_combined(task_v1_session, task_v2_session):
    TDESC = "twins, separated at birth (but no longer!)"

    # Task 1a - is unique
    t1a = Task_v1(desc=TDESC)
    t1a.first_scope = "2021-ww24.1"
    task_v1_session.add(t1a)
    task_v1_session.flush()

    tts = TaskTimeScope(task_id=t1a.task_id, time_scope_id=t1a.first_scope)
    task_v1_session.add(tts)
    del tts

    # Task 1b - has the same description
    t1b = Task_v1(desc=TDESC)
    t1b.first_scope = "2021-ww23.1"
    task_v1_session.add(t1b)
    task_v1_session.flush()

    tts = TaskTimeScope(task_id=t1b.task_id, time_scope_id=t1b.first_scope)
    task_v1_session.add(tts)
    del tts

    # Assert they're distinct
    task_v1_session.commit()

    q1 = Task_v1.query
    assert len(q1.all()) == 2

    # Check that there's only one new task
    migrate_tasks(task_v1_session, task_v2_session)

    q2 = Task_v2.query
    assert len(q2.all()) == 1
    assert q2.one().desc == TDESC
    assert len(q2.one().linkages) == 2


def test_orphans(task_v1_session, task_v2_session):
    t1a = Task_v1(desc="t1a", first_scope="2021-ww24.5")
    task_v1_session.add(t1a)
    task_v1_session.flush()

    t2 = None
    pass
