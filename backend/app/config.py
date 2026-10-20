"""Application configuration, loaded from environment variables."""
import os
import secrets
import warnings
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
INSTANCE_DIR = BASE_DIR / "instance"


def _resolve_database_url(url: str) -> str:
    """Resolve relative SQLite paths into backend/instance/ so the DB location
    never depends on the directory the server was started from.

    Hosted PostgreSQL providers (Neon, Render, Heroku) often hand out
    "postgres://" URLs, which SQLAlchemy 2 rejects; they are normalised here."""
    url = url.strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    prefix = "sqlite:///"
    if url.startswith(prefix) and url != "sqlite:///:memory:":
        path = Path(url[len(prefix):])
        if not path.is_absolute():
            INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
            return f"{prefix}{(INSTANCE_DIR / path).as_posix()}"
    return url


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _split_origins(value: str) -> list[str]:
    return [origin.strip() for origin in value.split(",") if origin.strip()]


class BaseConfig:
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Neon (and other serverless Postgres) closes idle connections; test each
    # pooled connection before use and recycle them well before that happens.
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}

    # Request header holding the real client IP when running behind a proxy
    # (Render: True-Client-IP). Empty = use the socket address (local dev).
    CLIENT_IP_HEADER = os.getenv("CLIENT_IP_HEADER", "").strip()

    JWT_TOKEN_LOCATION = ["headers"]
    JWT_HEADER_TYPE = "Bearer"
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        minutes=int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES_MINUTES", "60"))
    )

    CORS_ORIGINS = _split_origins(
        os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    )

    DEFAULT_PAGE_SIZE = 20
    MAX_PAGE_SIZE = 100
    CURRENCY = "INR"
    HOSTEL_NAME = os.getenv("HOSTEL_NAME", "HostelHub Residence")

    # Public URL of the React app; used to build links in emails.
    FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")

    # --- account policy ------------------------------------------------------
    STUDENT_SIGNUP_ENABLED = _env_bool("STUDENT_SIGNUP_ENABLED", True)
    # After verifying their email, students wait for staff approval.
    STUDENT_APPROVAL_REQUIRED = _env_bool("STUDENT_APPROVAL_REQUIRED", True)
    # Staff can apply without an invitation (an admin must approve them).
    STAFF_SIGNUP_ENABLED = _env_bool("STAFF_SIGNUP_ENABLED", True)
    EMAIL_VERIFICATION_REQUIRED = _env_bool("EMAIL_VERIFICATION_REQUIRED", True)
    EMAIL_VERIFICATION_TTL_HOURS = int(os.getenv("EMAIL_VERIFICATION_TTL_HOURS", "24"))
    PASSWORD_RESET_TTL_MINUTES = int(os.getenv("PASSWORD_RESET_TTL_MINUTES", "30"))
    STAFF_INVITATION_TTL_DAYS = int(os.getenv("STAFF_INVITATION_TTL_DAYS", "7"))

    # --- email ---------------------------------------------------------------
    # smtp: send through MAIL_SERVER.  file: development only - write each email
    # to backend/instance/dev-outbox/ instead of sending it.  memory: tests.
    MAIL_BACKEND = os.getenv("MAIL_BACKEND", "file").strip().lower()
    MAIL_SERVER = os.getenv("MAIL_SERVER", "")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USE_TLS = _env_bool("MAIL_USE_TLS", True)
    MAIL_USE_SSL = _env_bool("MAIL_USE_SSL", False)
    MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", "")
    MAIL_TIMEOUT_SECONDS = int(os.getenv("MAIL_TIMEOUT_SECONDS", "15"))
    # brevo: send through Brevo's HTTPS API (free plan). Works on hosts that
    # block outgoing SMTP ports, such as Render's free web services.
    BREVO_API_KEY = os.getenv("BREVO_API_KEY", "").strip()
    BREVO_API_URL = os.getenv("BREVO_API_URL", "https://api.brevo.com/v3/smtp/email").strip()

    @classmethod
    def load_secrets(cls, require: bool) -> None:
        """Read secrets from the environment. In production they are mandatory;
        in development an ephemeral key is generated (tokens die on restart)."""
        for name in ("SECRET_KEY", "JWT_SECRET_KEY"):
            value = os.getenv(name, "")
            if not value or value.startswith("replace-with"):
                if require:
                    raise RuntimeError(
                        f"{name} must be set to a strong random value in production."
                    )
                warnings.warn(
                    f"{name} is not set; using an ephemeral random key. "
                    "Set it in backend/.env (see .env.example).",
                    stacklevel=2,
                )
                value = secrets.token_urlsafe(64)
            setattr(cls, name, value)


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = _resolve_database_url(
        os.getenv("DATABASE_URL", "sqlite:///hostel.db")
    )


class ProductionConfig(BaseConfig):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = _resolve_database_url(
        os.getenv("DATABASE_URL", "sqlite:///hostel.db")
    )
    # Real email only. The file outbox would leave reset links on disk.
    MAIL_BACKEND = os.getenv("MAIL_BACKEND", "smtp").strip().lower()
    # Production defaults to the single frontend that FRONTEND_URL names.
    CORS_ORIGINS = _split_origins(os.getenv("CORS_ORIGINS", "")) or [BaseConfig.FRONTEND_URL]


class TestingConfig(BaseConfig):
    TESTING = True
    # Optional: run the suite against PostgreSQL, e.g.
    #   TEST_DATABASE_URL=postgresql://user@localhost/hms_test pytest
    SQLALCHEMY_DATABASE_URI = _resolve_database_url(
        os.getenv("TEST_DATABASE_URL", "sqlite:///:memory:"))
    SECRET_KEY = "test-secret-key-not-for-production"
    JWT_SECRET_KEY = "test-jwt-secret-key-not-for-production-use-only"
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=5)
    MAIL_BACKEND = "memory"
    FRONTEND_URL = "http://frontend.test"
    STUDENT_SIGNUP_ENABLED = True
    STUDENT_APPROVAL_REQUIRED = True
    STAFF_SIGNUP_ENABLED = True
    EMAIL_VERIFICATION_REQUIRED = True

    @classmethod
    def load_secrets(cls, require: bool) -> None:  # fixed keys for tests
        return None


CONFIGS = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}


def get_config(name: str | None):
    name = (name or os.getenv("FLASK_ENV") or "development").lower()
    if name not in CONFIGS:
        raise RuntimeError(f"Unknown configuration '{name}'. Use one of {list(CONFIGS)}.")
    config = CONFIGS[name]
    config.load_secrets(require=name == "production")
    allowed = {"production": {"smtp", "brevo"}, "testing": {"memory"}}.get(
        name, {"smtp", "brevo", "file"})
    if config.MAIL_BACKEND not in allowed:
        raise RuntimeError(f"MAIL_BACKEND={config.MAIL_BACKEND!r} is not allowed in {name}. "
                           f"Use one of: {', '.join(sorted(allowed))}.")
    if name == "production":
        _check_production(config)
    return config


def _check_production(config) -> None:
    """Fail fast on settings that would silently break a deployment."""
    problems = []
    if "localhost" in config.FRONTEND_URL or "127.0.0.1" in config.FRONTEND_URL:
        problems.append("FRONTEND_URL must be the public address of the frontend "
                        "(e.g. https://hostel-frontend.onrender.com); email links use it")
    if config.SQLALCHEMY_DATABASE_URI.startswith("sqlite") and not _env_bool(
            "ALLOW_SQLITE_IN_PRODUCTION", False):
        problems.append("DATABASE_URL must point to PostgreSQL (e.g. Neon). SQLite files are "
                        "erased on every restart of a free Render service. Set "
                        "ALLOW_SQLITE_IN_PRODUCTION=true only for a throw-away demo")
    if config.MAIL_BACKEND == "brevo" and not config.BREVO_API_KEY:
        problems.append("BREVO_API_KEY is required when MAIL_BACKEND=brevo")
    if config.MAIL_BACKEND in ("brevo", "smtp") and not config.MAIL_DEFAULT_SENDER:
        problems.append("MAIL_DEFAULT_SENDER is required (e.g. HostelHub <you@gmail.com>)")
    if problems:
        raise RuntimeError("Production configuration is incomplete:\n  - " + "\n  - ".join(problems))
