"""App factory, health check, error format and the create-admin command."""
from app.models import AuditLog, Role, User


def test_health_reports_database_ok(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.get_json()
    assert body["success"] is True
    assert body["data"]["database"] == "ok"


def test_unknown_route_returns_json_error(client):
    res = client.get("/api/does-not-exist")
    assert res.status_code == 404
    body = res.get_json()
    assert body["success"] is False
    assert body["error"]["code"] == "not_found"


def test_cors_allows_only_configured_origin(client):
    allowed = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert allowed.headers.get("Access-Control-Allow-Origin") == "http://localhost:5173"
    blocked = client.get("/api/health", headers={"Origin": "http://evil.example"})
    assert "Access-Control-Allow-Origin" not in blocked.headers


def test_create_admin_command(app, db, monkeypatch):
    runner = app.test_cli_runner()
    monkeypatch.setenv("HMS_ADMIN_PASSWORD", "Sup3rSecurePass")
    result = runner.invoke(args=["create-admin", "--email", "Head@Hostel.edu",
                                 "--full-name", "Head Admin"])
    assert result.exit_code == 0, result.output
    user = db.session.scalar(db.select(User).filter_by(email="head@hostel.edu"))
    assert user is not None and user.role == Role.ADMIN
    assert user.check_password("Sup3rSecurePass")
    assert db.session.scalar(db.select(AuditLog).filter_by(action="user.create_admin"))

    duplicate = runner.invoke(args=["create-admin", "--email", "head@hostel.edu",
                                    "--full-name", "Again"])
    assert duplicate.exit_code != 0
    assert "already exists" in duplicate.output


def test_create_admin_rejects_weak_password(app, db, monkeypatch):
    monkeypatch.setenv("HMS_ADMIN_PASSWORD", "short")
    result = app.test_cli_runner().invoke(
        args=["create-admin", "--email", "a@hostel.edu", "--full-name", "A"])
    assert result.exit_code != 0
    assert db.session.scalar(db.select(User)) is None
