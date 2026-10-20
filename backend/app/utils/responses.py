"""Success response helpers: {"success": true, "data": ..., "message"?: ...}."""
from flask import current_app, jsonify, request

from ..extensions import db


def success(data=None, status: int = 200, message: str | None = None):
    body = {"success": True, "data": data}
    if message:
        body["message"] = message
    return jsonify(body), status


def paginate(stmt, serializer):
    """Paginate a SELECT using ?page=&per_page= and serialise each row."""
    default = current_app.config["DEFAULT_PAGE_SIZE"]
    maximum = current_app.config["MAX_PAGE_SIZE"]
    page = max(request.args.get("page", 1, type=int) or 1, 1)
    per_page = min(max(request.args.get("per_page", default, type=int) or default, 1), maximum)
    result = db.paginate(stmt, page=page, per_page=per_page, error_out=False)
    return {
        "items": [serializer(item) for item in result.items],
        "pagination": {
            "page": result.page,
            "per_page": result.per_page,
            "total": result.total,
            "pages": result.pages,
        },
    }
