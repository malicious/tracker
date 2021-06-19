import io
import random
import secrets
import string

from tasks_v1.add import import_from_csv
from tasks_v1.models import Task as Task_v1, TaskTimeScope
from tasks_v2.migrate import do_one, do_multiple
from tasks_v2.models import Task as Task_v2


def _make_task(task_v1_session, scope_count=1) -> Task_v1:
    task_desc = ''.join(
        secrets.choice(string.ascii_uppercase) for _ in range(8))
    task_scope_id = f"{random.randint(1900, 2100)}-ww{random.randint(10, 50)}.{random.randint(1, 7)}"
    task = Task_v1(desc=task_desc, first_scope=task_scope_id)
    task_v1_session.add(task)
    task_v1_session.flush()

    tts1 = TaskTimeScope(task_id=task.task_id, time_scope_id=task.first_scope)
    task_v1_session.add(tts1)

    for n in range(scope_count-1):
        scope_id = f"{2000 + n}-ww44.4"
        tts = TaskTimeScope(task_id=task.task_id, time_scope_id=scope_id)
        task_v1_session.add(tts)

    task_v1_session.commit()
    return task


def test_migrate_zero(task_v1_session, task_v2_session):
    do_multiple(task_v1_session, task_v2_session)


def test_migrate_arbitrary(task_v1_session, task_v2_session):
    csv_test_file = """desc,scopes
"csv test file desc",2020-ww12.1 2019-ww14.5
"another one",2020-ww34
"another one",2020-ww52.4"""

    test_csv = io.StringIO(csv_test_file)
    import_from_csv(test_csv, task_v1_session)

    query = Task_v1.query
    assert query.first()

    do_multiple(task_v1_session, task_v2_session)

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

    do_one(task_v2_session, t1)
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

    do_one(task_v2_session, t1)
    t2 = Task_v2.query.one()
    assert t2.desc == TDESC
    assert len(t2.linkages) == 38


def disabled_test_duplicates_get_combined(task_v1_session, task_v2_session):
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
    do_multiple(task_v1_session, task_v2_session)

    q2 = Task_v2.query
    assert len(q2.all()) == 1
    assert q2.one().desc == TDESC
    assert len(q2.one().linkages) == 2


def test_orphan(task_v1_session, task_v2_session):
    t1 = _make_task(task_v1_session)
    t2 = do_one(task_v2_session, t1)
    assert t2.desc == t1.desc
    assert len(t1.scopes) == len(t2.linkages)


def _test_orphan(task_v1_session, task_v2_session, scope_count, first_scope_index):
    t1 = _make_task(task_v1_session, scope_count=scope_count)
    t1.first_scope = t1.scopes[first_scope_index].time_scope_id
    t1.resolution = "super unique resolution"
    t1.time_actual = 420
    task_v1_session.commit()

    t2 = do_one(task_v2_session, t1)
    assert t2.desc == t1.desc
    assert len(t1.scopes) == len(t2.linkages)

    # TODO: should really check scope migration, since we _force_day_scope()
    assert t1.first_scope == t2.linkages[first_scope_index].time_scope_id
    assert t2.linkages[first_scope_index].detailed_resolution
    assert t2.linkages[-1].resolution == t1.resolution
    assert t2.linkages[-1].time_elapsed == t1.time_actual


def test_orphan_where_created_is_first(task_v1_session, task_v2_session):
    _test_orphan(task_v1_session, task_v2_session, 7, 0)


def test_orphan_where_created_is_middle(task_v1_session, task_v2_session):
    _test_orphan(task_v1_session, task_v2_session, 7, 3)


def test_orphan_where_created_is_last(task_v1_session, task_v2_session):
    _test_orphan(task_v1_session, task_v2_session, 7, 6)


def test_2g_simple(task_v1_session, task_v2_session):
    t1a = _make_task(task_v1_session, 15)
    t1b = _make_task(task_v1_session, 1)
    t1b.parent_id = t1a.task_id

    t2 = do_one(task_v2_session, t1a)
    assert t2.desc == t1a.desc


def test_2g_conflict(task_v1_session, task_v2_session):
    t1a = None

