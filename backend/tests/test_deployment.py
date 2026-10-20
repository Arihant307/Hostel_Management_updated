"""Tests for deployment-related behaviour: production config checks, Brevo
email delivery, proxy-aware client IPs and the ensure-admin command."""
import json

import pytest

from app.models import Role, User


# ---------------------------------------------------------------- config
# Config classes read the environment at import time, so each case runs in a
# fresh Python process with a controlled environment.
import os
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent

GOOD_PROD = dict(
    DATABASE_URL="postgres://u:p@ep-x.neon.tech/neondb?sslmode=require",
    FRONTEND_URL="https://hostel-frontend.onrender.com",
    MAIL_BACKEND="brevo", BREVO_API_KEY="xkeysib-test",
    MAIL_DEFAULT_SENDER="HostelHub <warden@example.com>",
)

_PROBE = (
    # Ignore any developer backend/.env so only the environment below counts.
    "import dotenv; dotenv.load_dotenv = lambda *a, **k: False\n"
    "import json; from app.config import get_config\n"
    "try:\n"
    "    c = get_config('production')\n"
    "    print(json.dumps({'ok': True, 'db': c.SQLALCHEMY_DATABASE_URI, 'cors': c.CORS_ORIGINS,"
    " 'pre_ping': c.SQLALCHEMY_ENGINE_OPTIONS['pool_pre_ping']}))\n"
    "except RuntimeError as e:\n"
    "    print(json.dumps({'ok': False, 'error': str(e)}))\n"
)


def _production_config(**env):
    clean = {k: v for k, v in os.environ.items()
             if k not in GOOD_PROD and k not in ("CORS_ORIGINS", "ALLOW_SQLITE_IN_PRODUCTION",
                                                 "FLASK_ENV", "TEST_DATABASE_URL")}
    clean.update(SECRET_KEY="x" * 40, JWT_SECRET_KEY="y" * 40, **env)
    out = subprocess.run([sys.executable, "-c", _PROBE], cwd=BACKEND_DIR, env=clean,
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_production_config_accepts_complete_settings():
    result = _production_config(**GOOD_PROD)
    assert result["ok"], result
    # postgres:// is normalised for SQLAlchemy 2
    assert result["db"].startswith("postgresql://u:p@ep-x.neon.tech/")
    # CORS defaults to the frontend URL in production
    assert result["cors"] == ["https://hostel-frontend.onrender.com"]
    assert result["pre_ping"] is True


@pytest.mark.parametrize("override, message", [
    ({"FRONTEND_URL": None}, "FRONTEND_URL"),
    ({"DATABASE_URL": None}, "DATABASE_URL must point to PostgreSQL"),
    ({"BREVO_API_KEY": None}, "BREVO_API_KEY"),
    ({"MAIL_DEFAULT_SENDER": None}, "MAIL_DEFAULT_SENDER"),
    ({"MAIL_BACKEND": "file"}, "not allowed in production"),
])
def test_production_config_rejects_incomplete_settings(override, message):
    env = {k: v for k, v in {**GOOD_PROD, **override}.items() if v is not None}
    result = _production_config(**env)
    assert not result["ok"] and message in result["error"], result


def test_sqlite_allowed_in_production_only_when_opted_in():
    env = {k: v for k, v in GOOD_PROD.items() if k != "DATABASE_URL"}
    result = _production_config(ALLOW_SQLITE_IN_PRODUCTION="true", **env)
    assert result["ok"] and result["db"].startswith("sqlite:///"), result


def test_explicit_cors_origins_still_respected():
    result = _production_config(CORS_ORIGINS="https://a.example,https://b.example", **GOOD_PROD)
    assert result["cors"] == ["https://a.example", "https://b.example"]


# ---------------------------------------------------------------- brevo

class _FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return b'{"messageId":"<x@brevo>"}'


def _run_thread_inline(monkeypatch):
    import app.services.mailer as mailer

    class InlineThread:
        def __init__(self, target, args, daemon):
            self.target, self.args = target, args

        def start(self):
            self.target(*self.args)

    monkeypatch.setattr(mailer.threading, "Thread", InlineThread)
    return mailer


def test_brevo_backend_posts_expected_payload(app, monkeypatch):
    mailer = _run_thread_inline(monkeypatch)
    captured = {}

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.header_items())
        captured["body"] = json.loads(req.data)
        captured["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setattr(mailer.urlrequest, "urlopen", fake_urlopen)
    app.config.update(MAIL_BACKEND="brevo", BREVO_API_KEY="xkeysib-test",
                      MAIL_DEFAULT_SENDER="HostelHub <warden@example.com>")
    mailer.send_email("student@example.com", "Hello", "Plain text body", "<p>HTML body</p>")

    assert captured["url"] == "https://api.brevo.com/v3/smtp/email"
    assert captured["headers"]["Api-key"] == "xkeysib-test"
    body = captured["body"]
    assert body["sender"] == {"email": "warden@example.com", "name": "HostelHub"}
    assert body["to"] == [{"email": "student@example.com"}]
    assert body["subject"] == "Hello"
    assert body["textContent"].strip() == "Plain text body"
    assert body["htmlContent"].strip() == "<p>HTML body</p>"


def test_brevo_http_error_is_logged_not_raised(app, monkeypatch, caplog):
    mailer = _run_thread_inline(monkeypatch)
    import io
    from urllib.error import HTTPError

    def failing_urlopen(req, timeout):
        raise HTTPError(req.full_url, 401, "Unauthorized", {}, io.BytesIO(b'{"message":"Key not found"}'))

    monkeypatch.setattr(mailer.urlrequest, "urlopen", failing_urlopen)
    app.config.update(MAIL_BACKEND="brevo", BREVO_API_KEY="bad",
                      MAIL_DEFAULT_SENDER="warden@example.com")
    mailer.send_email("student@example.com", "Hello", "Body")  # must not raise
    assert "Brevo HTTP 401" in caplog.text and "Key not found" in caplog.text


def test_brevo_not_configured_logs_error(app, monkeypatch, caplog):
    mailer = _run_thread_inline(monkeypatch)
    called = []
    monkeypatch.setattr(mailer.urlrequest, "urlopen", lambda *a, **k: called.append(1))
    app.config.update(MAIL_BACKEND="brevo", BREVO_API_KEY="", MAIL_DEFAULT_SENDER="")
    mailer.send_email("student@example.com", "Hello", "Body")
    assert not called
    assert "BREVO_API_KEY" in caplog.text


def test_forgot_password_sends_reset_link_through_brevo(app, client, make_user, db, monkeypatch):
    mailer = _run_thread_inline(monkeypatch)
    sent = []
    monkeypatch.setattr(mailer.urlrequest, "urlopen",
                        lambda req, timeout: (sent.append(json.loads(req.data)), _FakeResponse())[1])
    app.config.update(MAIL_BACKEND="brevo", BREVO_API_KEY="k", MAIL_DEFAULT_SENDER="a@example.com")
    make_user(Role.STUDENT, email="reset.me@example.com")
    db.session.commit()
    r = client.post("/api/auth/forgot-password", json={"email": "reset.me@example.com"})
    assert r.status_code == 200
    assert len(sent) == 1
    assert sent[0]["to"] == [{"email": "reset.me@example.com"}]
    assert "http://frontend.test/reset-password?token=" in sent[0]["textContent"]


# ---------------------------------------------------------------- client ip

def test_client_ip_uses_configured_proxy_header(app):
    from app.utils.request import client_ip
    app.config["CLIENT_IP_HEADER"] = "True-Client-IP"
    with app.test_request_context(headers={"True-Client-IP": "203.0.113.7"},
                                  environ_base={"REMOTE_ADDR": "10.0.0.1"}):
        assert client_ip() == "203.0.113.7"
    with app.test_request_context(environ_base={"REMOTE_ADDR": "10.0.0.1"}):
        assert client_ip() == "10.0.0.1"  # header missing -> socket address


def test_client_ip_ignores_header_when_not_configured(app):
    from app.utils.request import client_ip
    app.config["CLIENT_IP_HEADER"] = ""
    with app.test_request_context(headers={"True-Client-IP": "203.0.113.7"},
                                  environ_base={"REMOTE_ADDR": "10.0.0.1"}):
        assert client_ip() == "10.0.0.1"


def test_login_throttle_is_per_real_client_behind_proxy(app, client, make_user, db):
    app.config["CLIENT_IP_HEADER"] = "True-Client-IP"
    make_user(Role.STUDENT, email="victim@example.com")
    db.session.commit()
    proxy = {"REMOTE_ADDR": "10.0.0.1"}
    for _ in range(5):
        client.post("/api/auth/login", json={"email": "victim@example.com", "password": "wrong"},
                    headers={"True-Client-IP": "198.51.100.1"}, environ_base=proxy)
    blocked = client.post("/api/auth/login", json={"email": "victim@example.com", "password": "wrong"},
                          headers={"True-Client-IP": "198.51.100.1"}, environ_base=proxy)
    assert blocked.status_code == 429
    # A different real user behind the same proxy is not affected.
    other = client.post("/api/auth/login",
                        json={"email": "victim@example.com", "password": "Str0ngPassword!"},
                        headers={"True-Client-IP": "198.51.100.2"}, environ_base=proxy)
    assert other.status_code == 200


# ---------------------------------------------------------------- ensure-admin

def _ensure_admin(app, monkeypatch, **env):
    for key in ("ADMIN_EMAIL", "ADMIN_PASSWORD", "ADMIN_NAME"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return app.test_cli_runner().invoke(args=["ensure-admin"])


def test_ensure_admin_creates_admin_once(app, monkeypatch, db, client):
    r = _ensure_admin(app, monkeypatch, ADMIN_EMAIL="Boss@Example.com",
                      ADMIN_PASSWORD="Adm1nPassword", ADMIN_NAME="Hostel Admin")
    assert r.exit_code == 0, r.output
    assert "created" in r.output
    user = db.session.scalar(db.select(User).filter_by(email="boss@example.com"))
    assert user.role == Role.ADMIN and user.full_name == "Hostel Admin"

    r = _ensure_admin(app, monkeypatch, ADMIN_EMAIL="boss@example.com", ADMIN_PASSWORD="Adm1nPassword")
    assert r.exit_code == 0 and "already exists" in r.output

    login = client.post("/api/auth/login", json={"email": "boss@example.com", "password": "Adm1nPassword"})
    assert login.status_code == 200


def test_ensure_admin_skips_without_email(app, monkeypatch):
    r = _ensure_admin(app, monkeypatch)
    assert r.exit_code == 0 and "skipping" in r.output


def test_ensure_admin_rejects_weak_password(app, monkeypatch, db):
    r = _ensure_admin(app, monkeypatch, ADMIN_EMAIL="boss@example.com", ADMIN_PASSWORD="short")
    assert r.exit_code != 0
    assert db.session.scalar(db.select(User).filter_by(email="boss@example.com")) is None


def test_ensure_admin_does_not_promote_existing_student(app, monkeypatch, db, make_user):
    make_user(Role.STUDENT, email="student@example.com")
    db.session.commit()
    r = _ensure_admin(app, monkeypatch, ADMIN_EMAIL="student@example.com", ADMIN_PASSWORD="Adm1nPassword")
    assert r.exit_code == 0 and "non-admin" in r.output
    user = db.session.scalar(db.select(User).filter_by(email="student@example.com"))
    assert user.role == Role.STUDENT
