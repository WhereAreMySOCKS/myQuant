"""Basic route tests that do not require akshare or live data."""
import pytest

akshare = pytest.importorskip("akshare", reason="akshare not installed")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.database import Base  # noqa: E402
from app.core.deps import get_db  # noqa: E402
from app.models.target import Target, TargetType  # noqa: E402
import app.models.target  # noqa: E402, F401 — register ORM models

TEST_DATABASE_URL = "sqlite:///:memory:"

_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
_TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


@pytest.fixture(scope="module", autouse=True)
def _create_tables():
    Base.metadata.create_all(bind=_engine)
    yield
    Base.metadata.drop_all(bind=_engine)


@pytest.fixture()
def db():
    session = _TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db):
    def _override():
        try:
            yield db
        finally:
            pass

    from app.main import app
    app.dependency_overrides[get_db] = _override
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


def _seed_target(db, code: str = "600519", name: str = "贵州茅台"):
    t = Target(
        code=code,
        name=name,
        type=TargetType.STOCK,
        buy_bias_rate=-0.08,
        sell_bias_rate=0.15,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


class TestDeleteAllTargets:
    def test_delete_all_empty_table(self, client, db):
        """Delete on empty table should return 0 deleted."""
        db.query(Target).delete()
        db.commit()
        resp = client.delete("/targets/all")
        assert resp.status_code == 200
        data = resp.json()
        assert data["deleted_count"] == 0

    def test_delete_all_with_records(self, client, db):
        """Delete should remove all existing targets."""
        db.query(Target).delete()
        db.commit()
        _seed_target(db, "600519", "贵州茅台")
        _seed_target(db, "000001", "平安银行")

        resp = client.delete("/targets/all")
        assert resp.status_code == 200
        data = resp.json()
        assert data["deleted_count"] == 2

        # Verify the table is empty
        assert db.query(Target).count() == 0


class TestGetTargets:
    def test_list_empty(self, client, db):
        db.query(Target).delete()
        db.commit()
        resp = client.get("/targets/")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_nonexistent_target(self, client, db):
        db.query(Target).delete()
        db.commit()
        resp = client.get("/targets/999999")
        assert resp.status_code == 404

    def test_get_existing_target(self, client, db):
        db.query(Target).delete()
        db.commit()
        t = _seed_target(db, "600519", "贵州茅台")
        resp = client.get(f"/targets/{t.code}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == "600519"
        assert data["name"] == "贵州茅台"
