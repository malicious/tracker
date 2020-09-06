import pytest

import tracker


@pytest.fixture
def test_client():
    test_app = tracker.create_app()
    test_client = test_app.test_client()

    with test_app.app_context():
        yield test_client
