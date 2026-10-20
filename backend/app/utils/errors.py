"""Consistent JSON error responses.

Every error leaves the API in the shape:
    {"success": false, "error": {"code": "...", "message": "...", "details": {...}}}
"""
from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException

from ..extensions import db


class APIError(Exception):
    """Raise from routes/services to return a controlled JSON error."""

    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, status_code: int | None = None,
                 code: str | None = None, details: dict | None = None):
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code
        self.details = details or {}


class ValidationError(APIError):
    status_code = 422
    code = "validation_error"


class NotFoundError(APIError):
    status_code = 404
    code = "not_found"


class ConflictError(APIError):
    status_code = 409
    code = "conflict"


class ForbiddenError(APIError):
    status_code = 403
    code = "forbidden"


def error_response(message: str, status_code: int, code: str, details: dict | None = None):
    body = {"success": False, "error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return jsonify(body), status_code


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(APIError)
    def handle_api_error(err: APIError):
        db.session.rollback()
        return error_response(err.message, err.status_code, err.code, err.details)

    @app.errorhandler(HTTPException)
    def handle_http_error(err: HTTPException):
        code = (err.name or "error").lower().replace(" ", "_")
        return error_response(err.description or err.name, err.code or 500, code)

    @app.errorhandler(Exception)
    def handle_unexpected(err: Exception):
        db.session.rollback()
        app.logger.exception("Unhandled error")
        # Never leak internals (stack traces, SQL) to clients.
        return error_response("An unexpected error occurred.", 500, "internal_error")
