import json
import logging
import sqlite3
from typing import Callable

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
        sql_like_filter: str,
        import_source_mapper: Callable[[str], str],
        tasks_db: TasksDB | None = None,
):
    logger.debug(f"import_from({sqlite_db_path}, {import_source_mapper})")
    if tasks_db is None:
        tasks_db = get_db()

    # Add a bunch of converters so we don't have to do our own datetime parsing
    sqlite3.register_converter('DATETIME', sqlite3.converters['TIMESTAMP'])
    conn_src = sqlite3.connect(sqlite_db_path, detect_types=sqlite3.PARSE_DECLTYPES)
    conn_src.row_factory = sqlite3.Row

    with conn_src:
        src_db = conn_src.cursor()

        # region Tasks import
        for task_row in src_db.execute(
                'SELECT * FROM Tasks '
                'WHERE import_source LIKE ?',
                (sql_like_filter,)
        ):
            new_task = Task(
                task_id=task_row['task_id'],
                import_source=import_source_mapper(task_row['import_source']),
                desc=task_row['desc'],
                desc_for_llm=task_row['desc_for_llm'],
                category=task_row['category'],
                time_estimate=task_row['time_estimate'],
            )
            tasks_db.add(new_task)
        # endregion

        # region TaskLinkages import
        # Bulk import all the TaskLinkages at once, rather than trying to map directly to Tasks.
        for tl_row in src_db.execute(
                'SELECT * FROM TaskLinkages '
                'WHERE import_source LIKE ?',
                (sql_like_filter,)
        ):
            new_tl = TaskLinkage(
                task_id=tl_row['task_id'],
                import_source=import_source_mapper(tl_row['import_source']),
                time_scope=tl_row['time_scope'],
                created_at=tl_row['created_at'],
                time_elapsed=tl_row['time_elapsed'],
                resolution=tl_row['resolution'],
                detailed_resolution=tl_row['detailed_resolution'],
            )
            tasks_db.add(new_tl)
        # endregion

        tasks_db.commit()


def export_to(
        sqlite_db_path: str,
        import_source_mapper: Callable[[str], str],
        tasks_db: TasksDB | None = None,
):
    """
    Opens `sqlite_db_path` with raw sqlite, and feed SQLAlchemy objects into it.
    """
    logger.debug(f"export_to({sqlite_db_path}, {import_source_mapper})")
    if tasks_db is None:
        tasks_db = get_db()

    conn_dst = sqlite3.connect(sqlite_db_path)

    with conn_dst:
        dest_db = conn_dst.cursor()
        dest_db.execute('PRAGMA journal_mode=wal')

        # region Tasks export
        dest_db.execute(
            'CREATE TABLE IF NOT EXISTS "Tasks" ('
            '    task_id INTEGER NOT NULL,'
            '    import_source VARCHAR NOT NULL,'
            '    "desc" VARCHAR NOT NULL,'
            '    desc_for_llm VARCHAR,'
            '    category VARCHAR,'
            '    time_estimate FLOAT,'
            '    PRIMARY KEY (task_id, import_source)'
            ')'
        )

        count = -1
        for count, t in enumerate(tasks_db.query(Task).all()):
            dest_db.execute(
                'INSERT OR IGNORE INTO Tasks VALUES (?,?,?,?,?,?)',
                (t.task_id, import_source_mapper(t.import_source), t.desc, t.desc_for_llm, t.category, t.time_estimate)
            )

        logger.info(f"Exported {count} Tasks to {sqlite_db_path}")
        # endregion

        # region TaskLinkages export
        dest_db.execute(
            'CREATE TABLE IF NOT EXISTS "TaskLinkages" ('
            '    task_id INTEGER NOT NULL,'
            '    import_source VARCHAR NOT NULL,'
            '    time_scope DATE NOT NULL,'
            '    created_at DATETIME NOT NULL,'
            '    time_elapsed FLOAT,'
            '    resolution VARCHAR,'
            '    detailed_resolution VARCHAR,'
            '    PRIMARY KEY (task_id, import_source, time_scope),'
            '    UNIQUE (task_id, import_source, time_scope),'
            '    FOREIGN KEY(task_id) REFERENCES "Tasks" (task_id),'
            '    FOREIGN KEY(import_source) REFERENCES "Tasks" (import_source)'
            ')'
        )

        count = -1
        for count, tl in enumerate(tasks_db.query(TaskLinkage).all()):
            dest_db.execute(
                'INSERT OR IGNORE INTO TaskLinkages VALUES (?,?,?,?,?,?,?)',
                (tl.task_id, import_source_mapper(tl.import_source), tl.time_scope, tl.created_at, tl.time_elapsed,
                 tl.resolution, tl.detailed_resolution)
            )

        logger.info(f"Exported {count} TaskLinkages to {sqlite_db_path}")
        # endregion
