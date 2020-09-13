import pytest

import tracker


@pytest.fixture(scope='session')
def test_app():
    settings_override = {
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': "sqlite://",
    }

    test_app = tracker.create_app(settings_override)
    with test_app.app_context():
        yield test_app


@pytest.fixture
def test_client(test_app):
    return test_app.test_client()


@pytest.fixture(scope="function", autouse=True)
def session(test_app):
    tracker.content_db.create_all()
    yield tracker.content_db.session
    tracker.content_db.session.rollback()
    tracker.content_db.drop_all()
