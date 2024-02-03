import sqlalchemy
from sqlalchemy.orm import scoped_session, sessionmaker

from tasks import Base

db_session = None


def load_v2_models(current_db_path: str):
    engine = sqlalchemy.create_engine(
        'sqlite:///' + current_db_path,
        connect_args={
            "check_same_thread": False,
        }
    )

    Base.metadata.create_all(bind=engine)

    # Create a Session object and bind it to the declarative_base
    global db_session
    db_session = scoped_session(sessionmaker(autocommit=False,
                                             autoflush=False,
                                             bind=engine))

    Base.query = db_session.query_property()
