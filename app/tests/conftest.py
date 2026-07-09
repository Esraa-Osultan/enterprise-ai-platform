"""
Shared test fixtures. Each test run gets its own throwaway data directory
so tests never depend on (or corrupt) real uploaded documents.
"""

import os
import shutil

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    test_data_dir = tmp_path / "data"
    monkeypatch.setenv("UPLOAD_DIR", str(test_data_dir / "uploads"))
    monkeypatch.setenv("VECTOR_STORE_DIR", str(test_data_dir / "vector_store"))
    monkeypatch.setenv("USERS_DB_PATH", str(test_data_dir / "users.json"))
    monkeypatch.setenv("LOG_FILE", str(test_data_dir / "app.log"))
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key")

    from app.core.config import get_settings

    get_settings.cache_clear()

    yield

    get_settings.cache_clear()
    if os.path.exists(test_data_dir):
        shutil.rmtree(test_data_dir, ignore_errors=True)


@pytest.fixture
def client(isolated_data_dir):
    from app.api.deps import get_document_service, get_vector_store
    from app.main import app

    get_vector_store.cache_clear()
    get_document_service.cache_clear()

    return TestClient(app)


@pytest.fixture
def auth_headers(client):
    client.post(
        "/auth/register",
        json={"username": "engineer1", "email": "eng1@valeo.com", "password": "secret123"},
    )
    response = client.post(
        "/auth/login",
        data={"username": "engineer1", "password": "secret123"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
