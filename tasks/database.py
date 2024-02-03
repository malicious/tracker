import sqlalchemy
from sqlalchemy.orm import scoped_session, sessionmaker, Session

from tasks.database_models import Base

_db_session: Session = None


def get_db() -> Session:
    return _db_session


def migrate_v2_models(db_path: str, v2_db_path: str) -> None:
    """
    Add two sqlalchemy.String columns: `import_source` and `desc_for_llm`.

    This database migration is pretty straightforward, fortunately.
    """
    pass


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
