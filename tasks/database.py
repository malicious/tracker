import os
import sqlite3

import sqlalchemy
from sqlalchemy.orm import scoped_session, sessionmaker, Session

from tasks.database_models import Base

_db_session: Session = None


def get_db() -> Session:
    return _db_session


def try_migrate_v2_models(
        db_path: str,
        v2_db_path: str,
        default_import_source: str = '',
) -> None:
    """
    Add two sqlalchemy.String columns: `import_source` and `desc_for_llm`.

    This database migration is pretty straightforward, fortunately.

    However, we intentionally don't/didn't write tests for this because it's not automateable enough.
    That is, we expect the end user to have to manually inspect + modify the results of the migration,
    with an external SQLite database tool.
    """
    if os.path.exists(db_path):
        return

    if not os.path.exists(v2_db_path):
        # No need to migrate, just continue and let Flask create the database
        return

    c_src_conn = sqlite3.connect(v2_db_path)
    # Providing a row_factory lets us index cells by column name
    c_src_conn.row_factory = sqlite3.Row
    c_dst_conn = sqlite3.connect(db_path)

    # Using a `with` statement auto-closes the connections, though we should really have just nested them
    with c_src_conn, c_dst_conn:
        c_src = c_src_conn.cursor()
        c_dst = c_dst_conn.cursor()

        c_dst.executescript('''
        CREATE TABLE IF NOT EXISTS "Tasks" (
            task_id INTEGER NOT NULL,
            import_source VARCHAR NOT NULL,
            "desc" VARCHAR NOT NULL,
            desc_for_llm VARCHAR,
            category VARCHAR,
            time_estimate FLOAT,
            PRIMARY KEY (task_id, import_source)
        );
        CREATE TABLE IF NOT EXISTS "TaskLinkages" (
            task_id INTEGER NOT NULL,
            import_source VARCHAR NOT NULL,
            time_scope DATE NOT NULL,
            created_at DATETIME NOT NULL,
            time_elapsed FLOAT,
            resolution VARCHAR,
            detailed_resolution VARCHAR,
            PRIMARY KEY (task_id, import_source, time_scope),
            UNIQUE (task_id, import_source, time_scope),
            FOREIGN KEY(task_id) REFERENCES "Tasks" (task_id),
            FOREIGN KEY(import_source) REFERENCES "Tasks" (import_source)
        );
        ''')

        for task_row in c_src.execute('SELECT * FROM Tasks'):
            c_dst.execute(
                'INSERT OR IGNORE INTO Tasks VALUES (?,?,?,?,?,?)',
                (
                    task_row['task_id'],
                    default_import_source,
                    task_row['desc'],
                    None,  # desc_for_llm
                    task_row['category'],
                    task_row['time_estimate'],
                ))

        for tl_row in c_src.execute('SELECT * FROM TaskLinkages'):
            c_dst.execute(
                'INSERT OR IGNORE INTO TaskLinkages VALUES (?,?,?,?,?,?,?)',
                (
                    tl_row['task_id'],
                    default_import_source,
                    tl_row['time_scope'],
                    tl_row['created_at'],
                    tl_row['time_elapsed'],
                    tl_row['resolution'],
                    tl_row['detailed_resolution'],
                )
            )


def load_database_models(db_path: str) -> None:
    engine = sqlalchemy.create_engine(
        'sqlite:///' + db_path,
        connect_args={
            "check_same_thread": False,
        }
    )

    Base.metadata.create_all(bind=engine)

    # Create a Session object and bind it to the declarative_base
    global _db_session
    _db_session = scoped_session(sessionmaker(autocommit=False,
                                             autoflush=False,
                                             bind=engine))

    Base.query = _db_session.query_property()
