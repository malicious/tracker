import sqlalchemy
from sqlalchemy.orm import scoped_session, sessionmaker

from notes_v2.models import Base
# noinspection PyUnresolvedReferences
from . import models

db_session = None


def load_models(current_db_path: str):
    engine = sqlalchemy.create_engine('sqlite:///' + current_db_path)

    Base.metadata.create_all(bind=engine)

    # Create a Session object and bind it to the declarative_base
    global db_session
    db_session = scoped_session(sessionmaker(autocommit=False,
                                             autoflush=False,
                                             bind=engine))

    Base.query = db_session.query_property()
