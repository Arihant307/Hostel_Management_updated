"""Unauthenticated health check used by the frontend and deployment probes."""
from flask import Blueprint, jsonify
from sqlalchemy import text

from ..extensions import db
from ..utils.time import isoformat, utcnow

bp = Blueprint("health", __name__)


@bp.get("/health")
def health():
    try:
        db.session.execute(text("SELECT 1"))
        database = "ok"
    except Exception:  # pragma: no cover - reported, not raised
        db.session.rollback()
        database = "unavailable"
    status = 200 if database == "ok" else 503
    return jsonify({
        "success": database == "ok",
        "data": {"status": "ok" if status == 200 else "degraded",
                 "database": database,
                 "time": isoformat(utcnow())},
    }), status
