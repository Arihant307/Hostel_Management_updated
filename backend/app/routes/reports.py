"""/api/reports — admin reports, CSV exports and the audit log.

CSV exports accept the same filters as the matching list endpoints. Cell
values that start with = + - @ are prefixed with ' so spreadsheet apps never
evaluate them as formulas (CSV injection).
"""
import csv
import io
from datetime import date

from flask import Blueprint, Response
from sqlalchemy import func, or_
from sqlalchemy.orm import selectinload

from ..extensions import db
from ..models import (
    AuditLog, FeeRecord, FeeType, Payment, PaymentMethod, PaymentStatus, Room, RoomAllocation,
    StudentProfile, User,
)
from ..services import stats
from ..services.billing import outstanding_expr
from ..utils.auth import admin_required
from ..utils.errors import NotFoundError
from ..utils.query import arg_date, arg_int, arg_str
from ..utils.responses import paginate, success
from ..utils.time import isoformat, today
from .fees import filtered_fees_stmt
from .payments import filtered_payments_stmt
from .rooms import filtered_rooms_stmt

bp = Blueprint("reports", __name__)


def _money(minor) -> str:
    return f"{(minor or 0) / 100:.2f}"


def _safe(value):
    if value is None:
        return ""
    text = str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def _csv_response(filename: str, header: list[str], rows) -> Response:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    for row in rows:
        writer.writerow([_safe(v) for v in row])
    stamped = f"{filename}-{today():%Y%m%d}.csv"
    return Response("﻿" + buffer.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{stamped}"'})


@bp.get("/summary")
@admin_required
def summary():
    end = arg_date("to") or today()
    months = min(max(arg_int("months") or 12, 1), 36)
    method_rows = db.session.execute(
        db.select(Payment.method, func.count(Payment.id), func.sum(Payment.amount_minor))
        .where(Payment.status == PaymentStatus.COMPLETED).group_by(Payment.method)).all()
    type_rows = db.session.execute(
        db.select(FeeRecord.fee_type, func.count(FeeRecord.id),
                  func.sum(FeeRecord.amount_due_minor), func.sum(outstanding_expr()))
        .where(FeeRecord.cancelled_at.is_(None)).group_by(FeeRecord.fee_type)).all()
    debtors = db.session.execute(
        db.select(StudentProfile.id, StudentProfile.student_code, User.full_name,
                  func.sum(outstanding_expr()).label("owed"))
        .join(FeeRecord.student).join(StudentProfile.user)
        .group_by(StudentProfile.id, StudentProfile.student_code, User.full_name)
        .having(func.sum(outstanding_expr()) > 0)
        .order_by(func.sum(outstanding_expr()).desc()).limit(10)).all()
    return success({
        "revenue_by_month": stats.payment_trend(end, months),
        "revenue_by_method": [{"method": m.value, "count": c, "amount_minor": int(a or 0)}
                              for m, c, a in method_rows],
        "fees_by_type": [{"fee_type": t.value, "count": c, "billed_minor": int(b or 0),
                          "outstanding_minor": int(o or 0)} for t, c, b, o in type_rows],
        "top_outstanding": [{"student_id": i, "student_code": code, "full_name": name,
                             "outstanding_minor": int(owed)} for i, code, name, owed in debtors],
        "occupancy_by_block": stats.occupancy_by_block(),
        "complaints": stats.complaint_totals(),
        "complaints_by_category": stats.complaints_by_category(),
        "totals": {"rooms": stats.bed_totals(), "fees": stats.fee_totals(today()),
                   "payments": stats.payment_totals(today())},
    })


@bp.get("/export/<kind>.csv")
@admin_required
def export(kind: str):
    if kind == "fees":
        fees = db.session.scalars(filtered_fees_stmt().order_by(FeeRecord.due_date.desc())).all()
        return _csv_response("fees", [
            "Fee ID", "Student ID", "Student name", "Fee type", "Description", "Period start",
            "Period end", "Due date", "Amount due", "Amount paid", "Balance", "Status",
        ], ([f.id, f.student.student_code, f.student.user.full_name, f.fee_type.value,
             f.description, f.period_start, f.period_end, f.due_date, _money(f.amount_due_minor),
             _money(f.amount_paid_minor), _money(f.balance_minor), f.status.value] for f in fees))
    if kind == "payments":
        payments = db.session.scalars(filtered_payments_stmt().order_by(Payment.paid_on.desc())).all()
        return _csv_response("payments", [
            "Receipt", "Paid on", "Student ID", "Student name", "Fee ID", "Fee type", "Amount",
            "Method", "Source", "Status", "Verified online", "Reference", "Recorded by",
        ], ([p.receipt_number, p.paid_on, p.fee_record.student.student_code,
             p.fee_record.student.user.full_name, p.fee_record_id, p.fee_record.fee_type.value,
             _money(p.amount_minor), p.method.value, p.source.value, p.status.value,
             "yes" if p.is_verified_online else "no", p.reference,
             p.recorded_by.full_name if p.recorded_by else ""] for p in payments))
    if kind == "students":
        students = db.session.scalars(
            db.select(StudentProfile).join(StudentProfile.user)
            .options(selectinload(StudentProfile.user),
                     selectinload(StudentProfile.allocations).selectinload(RoomAllocation.room))
            .order_by(StudentProfile.student_code)).all()
        def room_of(s):
            a = s.current_allocation
            return f"{a.room.block}-{a.room.room_number}" if a else ""
        return _csv_response("students", [
            "Student ID", "Name", "Email", "Phone", "Course", "Department", "Year",
            "Registered", "Room", "Account status", "Emergency contact", "Emergency phone",
        ], ([s.student_code, s.user.full_name, s.user.email, s.user.phone, s.course, s.department,
             s.academic_year, s.registration_date, room_of(s),
             "active" if s.user.is_active else "inactive", s.emergency_contact_name,
             s.emergency_contact_phone] for s in students))
    if kind == "rooms":
        rooms = db.session.scalars(filtered_rooms_stmt().order_by(Room.block, Room.room_number)).all()
        return _csv_response("rooms", [
            "Block", "Room", "Floor", "Type", "Capacity", "Occupied", "Available",
            "Monthly fee", "Status",
        ], ([r.block, r.room_number, r.floor, r.room_type.value, r.capacity, r.occupied_beds,
             r.available_beds, _money(r.monthly_fee_minor), r.occupancy_status] for r in rooms))
    raise NotFoundError("Unknown export. Use fees, payments, students or rooms.")


@bp.get("/audit-logs")
@admin_required
def audit_logs():
    stmt = db.select(AuditLog).options(selectinload(AuditLog.actor))
    if action := arg_str("action"):
        stmt = stmt.where(AuditLog.action.ilike(f"{action}%"))
    if entity := arg_str("entity_type"):
        stmt = stmt.where(AuditLog.entity_type == entity)
    if (actor_id := arg_int("actor_id")) is not None:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    if date_from := arg_date("from"):
        stmt = stmt.where(func.date(AuditLog.created_at) >= date_from.isoformat())
    if date_to := arg_date("to"):
        stmt = stmt.where(func.date(AuditLog.created_at) <= date_to.isoformat())
    stmt = stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    return success(paginate(stmt, lambda a: a.to_dict()))
