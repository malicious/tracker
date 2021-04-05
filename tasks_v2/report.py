from typing import Optional

from tasks.time_scope import TimeScope
from tasks_v2.models import Task


def report_one_task(task_id):
    task: Task = Task.query \
        .filter(Task.task_id == task_id) \
        .one_or_none()
    if not task:
        return {"error": f"invalid task_id: {task_id}"}

    return task.to_json_dict()


def report_tasks(page_scope: Optional[TimeScope]):
    return f"page_scope: {page_scope}"
