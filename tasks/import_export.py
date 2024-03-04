import json
import logging

from sqlalchemy import select, func, delete

from tasks.database import get_db, TasksDB
from tasks.database_models import Task, TaskLinkage

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def list_import_sources(
        sql_like_filter: str | None,
        pretty_print: bool = True,
        tasks_db: TasksDB | None = None,
):
    logger.debug(f"list_import_sources({sql_like_filter})")
    if tasks_db is None:
        tasks_db = get_db()

    query = (
        select(
            func.count(Task.task_id),
            Task.import_source,
        )
        .group_by(Task.import_source)
        .order_by(func.count(Task.task_id).desc())
    )
    if sql_like_filter is not None:
        query = query.where(Task.import_source.like(sql_like_filter))

    import_source_rows = tasks_db.execute(query).all()
    import_source_info = {row[1]: row[0] for row in import_source_rows}
    if not pretty_print:
        print(json.dumps(import_source_info, indent=2))
        return import_source_info

    else:
        # Keep column widths limited to 20 + 52-ish
        col0_header = "count"
        col0_max_entry_length = max(map(len, map(str, import_source_info.values())))
        col0_width = max(len(col0_header),
                         min(col0_max_entry_length + 1, 20))

        col1_header = "import_source"
        col1_max_entry_length = max(map(len, map(repr, import_source_info.keys())))
        col1_width = max(len(col1_header),
                         min(col1_max_entry_length, 72 - col0_width - 2))

        # Do the pretty-print with all these precomputed widths
        print()
        print(f"{col0_header:>{col0_width}} {col1_header: <{col1_width}}")
        print(f"{'-' * col0_width} {'-' * col1_width}")
        for import_source, count in import_source_info.items():
            print(f"{count:>{col0_width}} {repr(import_source): <{col1_width}}")


def delete_import_source(
        sql_like_filter: str,
        tasks_db: TasksDB | None = None,
):
    logger.debug(f"delete_import_source({sql_like_filter})")
    if tasks_db is None:
        tasks_db = get_db()

    linkage_count = tasks_db.query(TaskLinkage) \
        .where(TaskLinkage.import_source.like(sql_like_filter)) \
        .count()
    logger.info(f"TaskLinkages matching {repr(sql_like_filter)}: {linkage_count}")

    task_count = tasks_db.query(Task) \
        .where(Task.import_source.like(sql_like_filter)) \
        .count()
    logger.info(f"Tasks matching {repr(sql_like_filter)}: {task_count}")

    confirmation = input(f"Type {repr(sql_like_filter)} to confirm deletion: ")
    if confirmation != sql_like_filter:
        # TODO: Should this be print() or logger.error()?
        #  It should match the modality of input(), I think.
        print(f"Failed to confirm, exiting")
        return False

    tasks_db.execute(
        delete(TaskLinkage)
        .where(TaskLinkage.import_source.like(sql_like_filter))
    )
    tasks_db.execute(
        delete(Task)
        .where(Task.import_source.like(sql_like_filter))
    )
    tasks_db.commit()

    return True


def import_from(
        sqlite_db_path: str,
        default_import_source: str | None,
        override_import_source: str | None,
):
    print(f"import_from({sqlite_db_path}, {default_import_source}, {override_import_source})")


def export_to(
        sqlite_db_path: str,
        default_import_source: str | None,
        override_import_source: str | None,
):
    print(f"export_to({sqlite_db_path}, {default_import_source}, {override_import_source})")
