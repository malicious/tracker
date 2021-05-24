import pytest
from sqlalchemy.orm import Session

import tasks_v1
import tasks_v2
from tracker.app import create_app
from tracker.db import content_db


@pytest.fixture(scope='session')
def test_app():
    settings_override = {
        'TESTING': True,
        'SQLALCHEMY_BINDS': {
            'notes': 'sqlite://',
        },
        #'SQLALCHEMY_DATABASE_URI': 'sqlite://',
        #'SQLALCHEMY_ECHO': True,
    }

    test_app = create_app(settings_override)
    with test_app.app_context():
        yield test_app


@pytest.fixture
def test_client(test_app):
    return test_app.test_client()


@pytest.fixture(scope="function", autouse=True)
def session(test_app) -> Session:
    content_db.create_all()
    yield content_db.session
    content_db.session.rollback()
    content_db.drop_all()


@pytest.fixture(scope="function", autouse=True)
def task_v1_session() -> Session:
    tasks_v1.load_v1_models('')
    yield tasks_v1.db_session
    tasks_v1.db_session.remove()


@pytest.fixture(scope="function", autouse=True)
def task_v2_session() -> Session:
    tasks_v2.load_v2_models('')
    yield tasks_v2.db_session
    tasks_v2.db_session.remove()
