import pytest

from tracker.app import create_app
from tracker.content import content_db


@pytest.fixture(scope='session')
def test_app():
    settings_override = {
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': "sqlite://",
    }

    test_app = create_app(settings_override)
    with test_app.app_context():
        yield test_app


@pytest.fixture
def test_client(test_app):
    return test_app.test_client()


@pytest.fixture(scope="function", autouse=True)
def session(test_app):
    content_db.create_all()
    yield content_db.session
    content_db.session.rollback()
    content_db.drop_all()
