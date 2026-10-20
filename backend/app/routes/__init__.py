"""Blueprint registration."""
from flask import Flask

from .allocations import bp as allocations_bp
from .auth import bp as auth_bp
from .complaints import bp as complaints_bp
from .dashboard import bp as dashboard_bp
from .fees import bp as fees_bp
from .health import bp as health_bp
from .notices import bp as notices_bp
from .payments import bp as payments_bp
from .reports import bp as reports_bp
from .rooms import bp as rooms_bp
from .staff_accounts import bp as staff_accounts_bp
from .students import bp as students_bp


def register_blueprints(app: Flask) -> None:
    app.register_blueprint(health_bp, url_prefix="/api")
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(staff_accounts_bp, url_prefix="/api/auth")
    app.register_blueprint(students_bp, url_prefix="/api/students")
    app.register_blueprint(rooms_bp, url_prefix="/api/rooms")
    app.register_blueprint(allocations_bp, url_prefix="/api/allocations")
    app.register_blueprint(fees_bp, url_prefix="/api/fees")
    app.register_blueprint(payments_bp, url_prefix="/api/payments")
    app.register_blueprint(complaints_bp, url_prefix="/api/complaints")
    app.register_blueprint(notices_bp, url_prefix="/api/notices")
    app.register_blueprint(dashboard_bp, url_prefix="/api/dashboard")
    app.register_blueprint(reports_bp, url_prefix="/api/reports")
