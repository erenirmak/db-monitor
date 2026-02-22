import pytest

from backend import create_app


@pytest.fixture
def app():
    app = create_app()
    app.config.update(
        {
            "TESTING": True,
        }
    )
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


def test_login_page_loads(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert b"Login" in response.data
