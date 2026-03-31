import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import get_db
from app.models import Base

_ADMIN_SETUP = {
    "username": "admin",
    "display_name": "Admin User",
    "password": "securepass123",
}
_ADMIN_LOGIN = {"username": "admin", "password": "securepass123"}


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    # Enable FK enforcement for cascade deletes in SQLite tests.
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, conn_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db):
    def override_get_db():
        try:
            yield db
        finally:
            pass

    from app.main import app

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def authed_client(client):
    """A test client that is already authenticated as admin."""
    resp = client.post("/api/auth/setup", json=_ADMIN_SETUP)
    assert resp.status_code == 201, f"Setup failed: {resp.json()}"
    resp = client.post("/api/auth/login", json=_ADMIN_LOGIN)
    assert resp.status_code == 200, f"Login failed: {resp.json()}"
    return client
