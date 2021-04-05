from tasks_v2.models import Task
from tasks_v2.report import report_one_task


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
