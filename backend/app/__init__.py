"""Hostel Management System — Flask application factory."""
from pathlib import Path

from dotenv import load_dotenv

# Load backend/.env before config classes read os.environ.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from flask import Flask  # noqa: E402

from .config import get_config  # noqa: E402
from .extensions import cors, db, jwt, migrate  # noqa: E402


def create_app(config_name: str | None = None) -> Flask:
    app = Flask(__name__, instance_path=str(Path(__file__).resolve().parent.parent / "instance"))
    app.config.from_object(get_config(config_name))
    app.json.sort_keys = False  # keep {"success", "data"/"error"} in a readable order

    db.init_app(app)
    # render_as_batch lets Alembic alter SQLite tables safely (copy-and-move).
    migrate.init_app(app, db, render_as_batch=True,
                     directory=str(Path(__file__).resolve().parent.parent / "migrations"))
    jwt.init_app(app)
    cors.init_app(
        app,
        resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}},
        supports_credentials=False,
    )

    # Import models so they are registered with SQLAlchemy metadata (needed by migrations).
    from . import models  # noqa: F401

    from .utils.errors import register_error_handlers
    register_error_handlers(app)

    from .routes import register_blueprints
    register_blueprints(app)

    from .cli import register_cli
    register_cli(app)

    return app
