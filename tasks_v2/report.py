from typing import Optional

from tasks.time_scope import TimeScope


def report_one_task(task_id):
    return task_id


def report_tasks(page_scope: Optional[TimeScope]):
    return f"page_scope: {page_scope}"
