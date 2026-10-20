"""The Alembic migrations must build exactly the schema the models describe."""
import sqlite3

from flask_migrate import downgrade, upgrade

from app import create_app
from app.config import TestingConfig
from app.extensions import db


def _tables(path):
    with sqlite3.connect(path) as conn:
        return {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")} - {"alembic_version"}


def test_upgrade_and_downgrade(tmp_path, monkeypatch):
    db_file = tmp_path / "migrate.db"
    monkeypatch.setattr(TestingConfig, "SQLALCHEMY_DATABASE_URI",
                        f"sqlite:///{db_file.as_posix()}")
    app = create_app("testing")
    with app.app_context():
        upgrade()
        # Migrations must create exactly the tables the models define.
        assert _tables(db_file) == set(db.metadata.tables)
        assert {"users", "rooms", "room_allocations", "payments", "revoked_tokens"} <= _tables(db_file)

        with sqlite3.connect(db_file) as conn:
            index_sql = conn.execute(
                "SELECT sql FROM sqlite_master WHERE name="
                "'uq_room_allocations_one_active_per_student'").fetchone()[0]
        assert "WHERE status = 'active'" in index_sql

        downgrade(revision="base")
        assert _tables(db_file) == set()


def test_existing_users_keep_access_after_account_lifecycle_migration(tmp_path, monkeypatch):
    """Users created before self-signup existed must not be locked out."""
    from app.models import ApprovalStatus, Role, User

    db_file = tmp_path / "legacy.db"
    monkeypatch.setattr(TestingConfig, "SQLALCHEMY_DATABASE_URI",
                        f"sqlite:///{db_file.as_posix()}")
    app = create_app("testing")
    with app.app_context():
        upgrade(revision="d66827ac8e83")          # schema before this feature
        from werkzeug.security import generate_password_hash
        pw = generate_password_hash("LegacyPass123", method="scrypt")
        with sqlite3.connect(db_file) as conn:
            for email, role in (("legacy-admin@hostel.test", "admin"),
                                ("legacy-student@hostel.test", "student")):
                conn.execute(
                    "INSERT INTO users (email, password_hash, full_name, role, is_active, "
                    "token_version, created_at, updated_at) "
                    "VALUES (?, ?, 'Legacy', ?, 1, 0, '2026-01-01', '2026-01-01')",
                    (email, pw, role))
        upgrade()                                  # apply the new migration

        users = db.session.scalars(db.select(User)).all()
        assert all(u.approval_status == ApprovalStatus.APPROVED for u in users)
        assert all(u.email_verified_at is not None for u in users)
        assert {u.role for u in users} == {Role.ADMIN, Role.STUDENT}

        client = app.test_client()
        for email in ("legacy-admin@hostel.test", "legacy-student@hostel.test"):
            res = client.post("/api/auth/login", json={"email": email, "password": "LegacyPass123"})
            assert res.status_code == 200, res.get_json()
        db.session.remove()
        db.engine.dispose()
