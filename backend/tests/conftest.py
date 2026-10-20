import itertools
from datetime import date

import pytest

from app import create_app
from app.extensions import db as _db
from app.models import Role, Room, RoomType, StudentProfile, User

_counter = itertools.count(1)


@pytest.fixture()
def app():
    from app.utils.rate_limit import clear_all
    clear_all()
    app = create_app("testing")
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def auth_headers(app, db):
    """Return Authorization headers carrying a fresh token for `user`."""
    from app.utils.auth import issue_access_token

    def _headers(user):
        db.session.commit()
        return {"Authorization": f"Bearer {issue_access_token(user)}"}
    return _headers


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def db(app):
    return _db


@pytest.fixture()
def make_user(db):
    def _make(role=Role.STUDENT, email=None, password="Str0ngPassword!", **kwargs):
        n = next(_counter)
        from app.utils.time import utcnow
        kwargs.setdefault("email_verified_at", utcnow())  # existing-style trusted account
        user = User(email=email or f"user{n}@example.com",
                    full_name=kwargs.pop("full_name", f"User {n}"), role=role, **kwargs)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()
        return user
    return _make


@pytest.fixture()
def make_student(db, make_user):
    def _make(code=None, **kwargs):
        n = next(_counter)
        user = make_user(Role.STUDENT)
        profile = StudentProfile(
            user=user, student_code=code or f"STU{n:04d}", course="B.Tech",
            department=kwargs.pop("department", "Computer Science"),
            academic_year=kwargs.pop("academic_year", 2),
            emergency_contact_name="Parent", emergency_contact_phone="9876543210",
            registration_date=date(2026, 7, 1), **kwargs,
        )
        db.session.add(profile)
        db.session.flush()
        return profile
    return _make


@pytest.fixture()
def make_room(db):
    def _make(block="A", number=None, capacity=2, **kwargs):
        room = Room(block=block, room_number=number or str(100 + next(_counter)),
                    floor=kwargs.pop("floor", 1), room_type=kwargs.pop("room_type", RoomType.DOUBLE),
                    capacity=capacity, monthly_fee_minor=kwargs.pop("monthly_fee_minor", 500000),
                    **kwargs)
        db.session.add(room)
        db.session.flush()
        return room
    return _make


@pytest.fixture()
def admin_headers(make_user, auth_headers):
    return auth_headers(make_user(Role.ADMIN, full_name="Admin User"))


@pytest.fixture()
def warden_headers(make_user, auth_headers):
    return auth_headers(make_user(Role.WARDEN, full_name="Warden User"))


@pytest.fixture()
def student_headers(make_student, auth_headers):
    """Headers for a fresh student; the profile is available as .profile."""
    profile = make_student()
    headers = auth_headers(profile.user)
    headers_obj = type("StudentHeaders", (dict,), {})(headers)
    headers_obj.profile = profile
    return headers_obj
