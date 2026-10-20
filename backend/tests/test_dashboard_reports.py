"""Dashboard figures come from real records; reports, CSV exports and audit log."""
import csv
import io
from datetime import date, timedelta

import pytest

from app.models import (
    AllocationStatus, Complaint, ComplaintCategory, ComplaintStatus, FeeRecord, FeeType, Notice,
    Payment, PaymentMethod, PaymentSource, PaymentStatus, Role, RoomAllocation,
)
from app.utils.time import today, utcnow


@pytest.fixture()
def seeded(db, make_room, make_student, make_user):
    """2 blocks / 3 rooms / 6 beds, 3 housed students, fees, payments, complaints."""
    admin = make_user(Role.ADMIN)
    a1 = make_room(block="A", number="101", capacity=2)
    a2 = make_room(block="A", number="102", capacity=1)
    b1 = make_room(block="B", number="201", capacity=3)
    make_room(block="C", number="301", capacity=4, is_active=False)  # ignored: inactive
    s1, s2, s3, idle = make_student(), make_student(), make_student(), make_student()
    for s, r in ((s1, a1), (s2, a1), (s3, b1)):
        db.session.add(RoomAllocation(student=s, room=r, allocated_on=date(2026, 8, 1)))
    month_start = today().replace(day=1)
    fees = [
        FeeRecord(student=s1, fee_type=FeeType.HOSTEL_RENT, period_start=month_start,
                  period_end=month_start + timedelta(days=27), due_date=today() - timedelta(days=1),
                  amount_due_minor=500000),  # overdue, unpaid
        FeeRecord(student=s2, fee_type=FeeType.HOSTEL_RENT, period_start=month_start,
                  period_end=month_start + timedelta(days=27), due_date=today() + timedelta(days=9),
                  amount_due_minor=500000),  # partially paid
        FeeRecord(student=s3, fee_type=FeeType.MESS, period_start=month_start,
                  period_end=month_start + timedelta(days=27), due_date=today() + timedelta(days=9),
                  amount_due_minor=300000),  # paid
    ]
    db.session.add_all(fees)
    db.session.flush()
    db.session.add_all([
        Payment(fee_record=fees[1], receipt_number="R-1", amount_minor=200000,
                method=PaymentMethod.UPI, source=PaymentSource.MANUAL,
                status=PaymentStatus.COMPLETED, paid_on=today(), recorded_by=admin),
        Payment(fee_record=fees[2], receipt_number="R-2", amount_minor=300000,
                method=PaymentMethod.CASH, source=PaymentSource.MANUAL,
                status=PaymentStatus.COMPLETED, paid_on=today(), recorded_by=admin),
        Payment(fee_record=fees[2], receipt_number="R-3", amount_minor=999,
                method=PaymentMethod.CASH, source=PaymentSource.MANUAL,
                status=PaymentStatus.REVERSED, paid_on=today(), recorded_by=admin),
    ])
    db.session.add_all([
        Complaint(student=s1, category=ComplaintCategory.PLUMBING, title="Tap", description="Leaks a lot"),
        Complaint(student=s3, category=ComplaintCategory.ELECTRICAL, title="Fan", description="Fan broken",
                  status=ComplaintStatus.RESOLVED, resolution="Fixed", resolved_at=utcnow()),
    ])
    db.session.add(Notice(title="Welcome", body="Hello students"))
    db.session.commit()
    return {"s1": s1, "idle": idle, "a2": a2}


def test_staff_dashboard_figures(client, seeded, warden_headers):
    res = client.get("/api/dashboard/summary", headers=warden_headers)
    assert res.status_code == 200
    d = res.get_json()["data"]
    assert d["students"]["total"] == 4 and d["students"]["with_room"] == 3
    assert d["students"]["without_room"] == 1
    assert d["rooms"] == {"rooms": 3, "beds_total": 6, "beds_occupied": 3, "beds_available": 3,
                          "occupancy_percent": 50.0}
    assert d["fees"] == {"outstanding_minor": 800000, "overdue_count": 1,
                         "overdue_minor": 500000, "unpaid_count": 2}
    assert d["payments"]["total_minor"] == 500000  # reversed payment excluded
    assert d["payments"]["this_month_minor"] == 500000
    assert d["complaints"]["active"] == 1 and d["complaints"]["resolved"] == 1
    assert len(d["payment_trend"]) == 12
    assert d["payment_trend"][-1]["amount_minor"] == 500000
    blocks = {b["block"]: b for b in d["occupancy_by_block"]}
    assert set(blocks) == {"A", "B"}
    assert (blocks["A"]["beds"], blocks["A"]["occupied"]) == (3, 2)
    assert len(d["recent_students"]) == 4 and len(d["recent_allocations"]) == 3


def test_dashboard_reflects_new_records(client, db, seeded, admin_headers):
    before = client.get("/api/dashboard/summary", headers=admin_headers).get_json()["data"]
    client.post("/api/allocations", headers=admin_headers,
                json={"student_id": seeded["idle"].id, "room_id": seeded["a2"].id})
    after = client.get("/api/dashboard/summary", headers=admin_headers).get_json()["data"]
    assert after["rooms"]["beds_occupied"] == before["rooms"]["beds_occupied"] + 1


def test_students_cannot_see_staff_dashboard(client, student_headers):
    assert client.get("/api/dashboard/summary", headers=student_headers).status_code == 403


def test_student_dashboard(client, db, seeded, auth_headers):
    s1 = seeded["s1"]
    d = client.get("/api/dashboard/student", headers=auth_headers(s1.user)).get_json()["data"]
    assert d["room"]["room_number"] == "101"
    assert len(d["room"]["roommates"]) == 1
    assert d["fees"]["outstanding_minor"] == 500000 and d["fees"]["overdue_count"] == 1
    assert d["fees"]["next_due"]["status"] == "overdue"
    assert [c["title"] for c in d["complaints"]] == ["Tap"]
    assert [n["title"] for n in d["notices"]] == ["Welcome"]


def test_staff_cannot_use_student_dashboard(client, warden_headers):
    assert client.get("/api/dashboard/student", headers=warden_headers).status_code == 403


def test_reports_summary(client, seeded, admin_headers, warden_headers):
    assert client.get("/api/reports/summary", headers=warden_headers).status_code == 403
    d = client.get("/api/reports/summary", headers=admin_headers).get_json()["data"]
    methods = {m["method"]: m["amount_minor"] for m in d["revenue_by_method"]}
    assert methods == {"upi": 200000, "cash": 300000}
    by_type = {t["fee_type"]: t for t in d["fees_by_type"]}
    assert by_type["hostel_rent"]["outstanding_minor"] == 800000
    assert d["top_outstanding"][0]["outstanding_minor"] == 500000
    assert len(d["revenue_by_month"]) == 12


def _rows(res):
    text = res.get_data(as_text=True).lstrip("﻿")
    return list(csv.reader(io.StringIO(text)))


def test_csv_exports(client, seeded, admin_headers):
    fees = client.get("/api/reports/export/fees.csv?status=overdue", headers=admin_headers)
    assert fees.status_code == 200 and fees.mimetype == "text/csv"
    assert "attachment" in fees.headers["Content-Disposition"]
    rows = _rows(fees)
    assert rows[0][0] == "Fee ID" and len(rows) == 2 and rows[1][-1] == "overdue"
    assert rows[1][8] == "5000.00"

    payments = _rows(client.get("/api/reports/export/payments.csv", headers=admin_headers))
    assert len(payments) == 4  # header + 3 (incl. reversed)
    students = _rows(client.get("/api/reports/export/students.csv", headers=admin_headers))
    assert len(students) == 5
    rooms = _rows(client.get("/api/reports/export/rooms.csv?is_active=true", headers=admin_headers))
    assert len(rooms) == 4
    assert client.get("/api/reports/export/secrets.csv", headers=admin_headers).status_code == 404


def test_csv_injection_is_neutralised(client, db, seeded, admin_headers):
    s1 = seeded["s1"]
    s1.user.full_name = "=HYPERLINK(\"http://evil\")"
    db.session.commit()
    rows = _rows(client.get("/api/reports/export/students.csv", headers=admin_headers))
    names = [r[1] for r in rows[1:]]
    assert "'=HYPERLINK(\"http://evil\")" in names


def test_exports_require_admin(client, warden_headers, student_headers):
    assert client.get("/api/reports/export/fees.csv", headers=warden_headers).status_code == 403
    assert client.get("/api/reports/export/fees.csv", headers=student_headers).status_code == 403


def test_audit_log_endpoint(client, admin_headers, warden_headers):
    client.post("/api/rooms", headers=admin_headers,
                json={"block": "Q", "room_number": "1", "floor": 0, "room_type": "single",
                      "capacity": 1, "monthly_fee_minor": 1000})
    logs = client.get("/api/reports/audit-logs?action=room.", headers=admin_headers).get_json()["data"]
    assert logs["items"][0]["action"] == "room.create"
    assert logs["items"][0]["actor"]["full_name"] == "Admin User"
    assert client.get("/api/reports/audit-logs", headers=warden_headers).status_code == 403
