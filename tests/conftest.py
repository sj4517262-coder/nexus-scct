import pytest
from fastapi.testclient import TestClient
from nexus.api import create_app


@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path / "test.db")


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


@pytest.fixture
def owner(client):
    response = client.post("/api/v1/auth/setup", json={"email": "owner@example.com", "password": "test-passphrase-123"})
    assert response.status_code == 201
    return client
