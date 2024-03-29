import pytest
from sqlalchemy.orm import Session

import notes_v2
import tasks
import tasks.database
import tasks.flask
from tracker.app import create_app


@pytest.fixture(scope='session')
def test_app():
    settings_override = {
        'TESTING': True,
    }

    test_app = create_app(settings_override)
    with test_app.app_context():
        yield test_app


@pytest.fixture
def test_client(test_app):
    return test_app.test_client()


@pytest.fixture(scope="function", autouse=True)
def note_v2_session(test_app) -> Session:
    notes_v2.load_models_pytest()
    yield notes_v2.db_session
    notes_v2.db_session.remove()
    notes_v2.db_session = None


@pytest.fixture(scope="function", autouse=True)
def tasks_db() -> Session:
    tasks.database.load_database_models('')
    yield tasks.database.get_db()
    tasks.database.get_db().remove()
    tasks.database._db_session = None
