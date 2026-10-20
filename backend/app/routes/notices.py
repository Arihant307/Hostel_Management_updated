"""/api/notices — notice board.

Staff (admins and wardens) publish, edit and delete notices. Students see only
notices that are currently active and addressed to all or to students.
Pinned notices are listed first.
"""
from datetime import datetime, timezone

from flask import Blueprint
from flask_jwt_extended import current_user
from sqlalchemy import or_

from ..extensions import db
from ..models import Notice, NoticeAudience, NoticeCategory
from ..services import audit
from ..utils.auth import login_required, staff_required
from ..utils.errors import APIError, NotFoundError
from ..utils.query import arg_choice, arg_str, is_student
from ..utils.request import Validator, json_body
from ..utils.responses import paginate, success
from ..utils.time import utcnow

bp = Blueprint("notices", __name__)


def _parse_datetime(value, field, errors):
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        errors[field] = "Must be a date-time (YYYY-MM-DDTHH:MM)."
        return None
    # Timestamps are stored as naive UTC; offset-less input is taken as UTC.
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _validate(data: dict, partial: bool, existing: Notice | None = None) -> dict:
    v = Validator(data, partial=partial)
    v.string("title", min_length=3, max_length=150)
    v.string("body", min_length=3, max_length=8000)
    v.choice("category", NoticeCategory, required=False)
    v.choice("audience", NoticeAudience, required=False)
    v.boolean("is_pinned", required=False)
    clean = v.clean
    for field in ("publish_at", "expires_at"):
        if field in data:
            clean[field] = _parse_datetime(data.get(field), field, v.errors)
    publish_at = clean.get("publish_at") or (existing.publish_at if existing else utcnow())
    expires_at = clean["expires_at"] if "expires_at" in clean else (existing.expires_at if existing else None)
    if expires_at and expires_at <= publish_at:
        v.errors["expires_at"] = "Expiry must be after the publish time."
    v.raise_if_errors()
    return clean


def _get_notice(notice_id: int) -> Notice:
    notice = db.session.get(Notice, notice_id)
    if notice is None:
        raise NotFoundError("Notice not found.")
    if is_student() and not (notice.is_active and notice.audience in
                             (NoticeAudience.ALL, NoticeAudience.STUDENTS)):
        raise NotFoundError("Notice not found.")
    return notice


@bp.get("")
@login_required
def list_notices():
    now = utcnow()
    stmt = db.select(Notice)
    if is_student():
        stmt = stmt.where(Notice.active_filter(now),
                          Notice.audience.in_([NoticeAudience.ALL, NoticeAudience.STUDENTS]))
    else:
        state = arg_choice("state", ["active", "scheduled", "expired"])
        if state == "active":
            stmt = stmt.where(Notice.active_filter(now))
        elif state == "scheduled":
            stmt = stmt.where(Notice.publish_at > now)
        elif state == "expired":
            stmt = stmt.where(Notice.expires_at.is_not(None), Notice.expires_at <= now)
        if audience := arg_choice("audience", NoticeAudience):
            stmt = stmt.where(Notice.audience == NoticeAudience(audience))
    if category := arg_choice("category", NoticeCategory):
        stmt = stmt.where(Notice.category == NoticeCategory(category))
    if search := arg_str("search"):
        like = f"%{search}%"
        stmt = stmt.where(or_(Notice.title.ilike(like), Notice.body.ilike(like)))
    stmt = stmt.order_by(Notice.is_pinned.desc(), Notice.publish_at.desc(), Notice.id.desc())
    return success(paginate(stmt, lambda n: n.to_dict()))


@bp.post("")
@staff_required
def create_notice():
    data = _validate(json_body(), partial=False)
    notice = Notice(title=data["title"], body=data["body"],
                    category=NoticeCategory(data.get("category") or "general"),
                    audience=NoticeAudience(data.get("audience") or "all"),
                    is_pinned=bool(data.get("is_pinned")),
                    publish_at=data.get("publish_at") or utcnow(),
                    expires_at=data.get("expires_at"),
                    created_by=current_user._get_current_object())
    db.session.add(notice)
    db.session.flush()
    audit.record("notice.create", "notice", notice.id, {"title": notice.title})
    db.session.commit()
    return success(notice.to_dict(), 201, "Notice published.")


@bp.get("/<int:notice_id>")
@login_required
def get_notice(notice_id: int):
    return success(_get_notice(notice_id).to_dict())


@bp.patch("/<int:notice_id>")
@staff_required
def update_notice(notice_id: int):
    notice = _get_notice(notice_id)
    data = _validate(json_body(), partial=True, existing=notice)
    for field, value in data.items():
        if field in ("title", "body") and value is None:
            raise APIError(f"{field.title()} cannot be empty.", 422, "validation_error")
        if field == "category" and value:
            value = NoticeCategory(value)
        if field == "audience" and value:
            value = NoticeAudience(value)
        if field == "publish_at" and value is None:
            continue
        setattr(notice, field, value)
    audit.record("notice.update", "notice", notice.id, {"fields": sorted(data)})
    db.session.commit()
    return success(notice.to_dict(), message="Notice updated.")


@bp.delete("/<int:notice_id>")
@staff_required
def delete_notice(notice_id: int):
    notice = _get_notice(notice_id)
    audit.record("notice.delete", "notice", notice.id, {"title": notice.title})
    db.session.delete(notice)
    db.session.commit()
    return success(None, message="Notice deleted.")
