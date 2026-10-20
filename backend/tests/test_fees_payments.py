"""Fee assignment, payment recording, status derivation, reversal and receipts."""
from datetime import date, timedelta

import pytest

from app.models import AuditLog, FeeRecord, Payment, RoomAllocation
from app.utils.time import today

FUTURE = (today() + timedelta(days=20)).isoformat()
PAST = (today() - timedelta(days=5)).isoformat()


def _fee(client, headers, student, **overrides):
    body = {"student_id": student.id, "fee_type": "hostel_rent", "period_start": "2026-10-01",
            "period_end": "2026-10-31", "due_date": FUTURE, "amount_due_minor": 600000,
            "description": "October rent", **overrides}
    return client.post("/api/fees", headers=headers, json=body)


def _pay(client, headers, fee_id, amount, **overrides):
    body = {"fee_record_id": fee_id, "amount_minor": amount, "method": "cash", **overrides}
    return client.post("/api/payments", headers=headers, json=body)


@pytest.fixture()
def student(make_student, db):
    s = make_student()
    db.session.commit()
    return s


def test_assign_fee(client, admin_headers, student):
    res = _fee(client, admin_headers, student)
    assert res.status_code == 201, res.get_json()
    data = res.get_json()["data"]
    assert (data["status"], data["balance_minor"], data["amount_paid_minor"]) == \
        ("pending", 600000, 0)


def test_fee_validation_and_duplicates(client, admin_headers, student):
    assert _fee(client, admin_headers, student, amount_due_minor=0).status_code == 422
    assert _fee(client, admin_headers, student, fee_type="parking").status_code == 422
    assert _fee(client, admin_headers, student, period_end="2026-09-01").status_code == 422
    assert _fee(client, admin_headers, student).status_code == 201
    dup = _fee(client, admin_headers, student)
    assert dup.status_code == 409 and dup.get_json()["error"]["code"] == "duplicate_fee"


def test_only_admin_manages_fees_and_payments(client, admin_headers, warden_headers, student):
    assert _fee(client, warden_headers, student).status_code == 403
    fee_id = _fee(client, admin_headers, student).get_json()["data"]["id"]
    assert _pay(client, warden_headers, fee_id, 100).status_code == 403
    assert client.get("/api/fees", headers=warden_headers).status_code == 200  # read-only


def test_payment_lifecycle_and_status(client, db, admin_headers, student):
    fee_id = _fee(client, admin_headers, student).get_json()["data"]["id"]

    first = _pay(client, admin_headers, fee_id, 200000)
    assert first.status_code == 201, first.get_json()
    p = first.get_json()["data"]
    assert p["source"] == "manual" and p["status"] == "completed"
    assert p["is_verified_online"] is False
    assert p["receipt_number"].startswith("RCPT-")
    fee = client.get(f"/api/fees/{fee_id}", headers=admin_headers).get_json()["data"]
    assert (fee["status"], fee["balance_minor"]) == ("partially_paid", 400000)

    over = _pay(client, admin_headers, fee_id, 400001)
    assert over.status_code == 422 and over.get_json()["error"]["code"] == "overpayment"

    upi = _pay(client, admin_headers, fee_id, 400000, method="upi", reference="UPI-778899")
    assert upi.status_code == 201
    fee = client.get(f"/api/fees/{fee_id}", headers=admin_headers).get_json()["data"]
    assert (fee["status"], fee["balance_minor"], len(fee["payments"])) == ("paid", 0, 2)

    assert _pay(client, admin_headers, fee_id, 1).get_json()["error"]["code"] == "fee_paid"
    assert db.session.scalar(db.select(AuditLog).filter_by(action="payment.record"))


def test_payment_validation(client, admin_headers, student):
    fee_id = _fee(client, admin_headers, student).get_json()["data"]["id"]
    no_ref = _pay(client, admin_headers, fee_id, 100, method="bank_transfer")
    assert "reference" in no_ref.get_json()["error"]["details"]["fields"]
    future = _pay(client, admin_headers, fee_id, 100, paid_on=(today() + timedelta(1)).isoformat())
    assert "paid_on" in future.get_json()["error"]["details"]["fields"]
    assert _pay(client, admin_headers, fee_id, -5).status_code == 422
    assert _pay(client, admin_headers, 9999, 100).status_code == 404


def test_client_cannot_mark_payment_verified(client, db, admin_headers, student):
    """Extra fields like status/source/verified_at in the request are ignored."""
    fee_id = _fee(client, admin_headers, student).get_json()["data"]["id"]
    res = _pay(client, admin_headers, fee_id, 1000, source="gateway", status="completed",
               verified_at="2026-10-01T00:00:00", gateway_transaction_id="fake")
    data = res.get_json()["data"]
    assert data["source"] == "manual" and data["is_verified_online"] is False
    payment = db.session.get(Payment, data["id"])
    assert payment.gateway_transaction_id is None and payment.verified_at is None


def test_reversal_restores_balance(client, admin_headers, student):
    fee_id = _fee(client, admin_headers, student).get_json()["data"]["id"]
    pid = _pay(client, admin_headers, fee_id, 600000).get_json()["data"]["id"]
    assert client.post(f"/api/payments/{pid}/reverse", headers=admin_headers,
                       json={"reason": ""}).status_code == 422
    res = client.post(f"/api/payments/{pid}/reverse", headers=admin_headers,
                      json={"reason": "Cheque bounced"})
    assert res.status_code == 200 and res.get_json()["data"]["status"] == "reversed"
    fee = client.get(f"/api/fees/{fee_id}", headers=admin_headers).get_json()["data"]
    assert (fee["status"], fee["balance_minor"]) == ("pending", 600000)
    assert client.post(f"/api/payments/{pid}/reverse", headers=admin_headers,
                       json={"reason": "again"}).status_code == 409


def test_overdue_status_and_filters(client, admin_headers, make_student, db):
    a, b, c = make_student(), make_student(), make_student()
    db.session.commit()
    overdue_id = _fee(client, admin_headers, a, due_date=PAST).get_json()["data"]["id"]
    pending_id = _fee(client, admin_headers, b).get_json()["data"]["id"]
    paid_id = _fee(client, admin_headers, c, amount_due_minor=1000).get_json()["data"]["id"]
    _pay(client, admin_headers, paid_id, 1000)

    def ids(qs):
        data = client.get(f"/api/fees?{qs}", headers=admin_headers).get_json()["data"]
        return sorted(f["id"] for f in data["items"]), data["totals"]

    assert ids("status=overdue")[0] == [overdue_id]
    assert ids("status=pending")[0] == [pending_id]
    assert ids("status=paid")[0] == [paid_id]
    assert ids("status=outstanding")[0] == sorted([overdue_id, pending_id])
    _, totals = ids("")
    assert totals == {"billed_minor": 1201000, "paid_minor": 1000, "outstanding_minor": 1200000}
    assert ids(f"student_id={a.id}")[0] == [overdue_id]
    assert ids("fee_type=mess")[0] == []


def test_cancel_fee_rules(client, admin_headers, student):
    fee_id = _fee(client, admin_headers, student).get_json()["data"]["id"]
    pid = _pay(client, admin_headers, fee_id, 100).get_json()["data"]["id"]
    blocked = client.post(f"/api/fees/{fee_id}/cancel", headers=admin_headers,
                          json={"reason": "Billed in error"})
    assert blocked.get_json()["error"]["code"] == "has_payments"
    client.post(f"/api/payments/{pid}/reverse", headers=admin_headers, json={"reason": "Refunded"})
    ok = client.post(f"/api/fees/{fee_id}/cancel", headers=admin_headers,
                     json={"reason": "Billed in error"})
    assert ok.get_json()["data"]["status"] == "cancelled"
    assert _pay(client, admin_headers, fee_id, 100).get_json()["error"]["code"] == "fee_cancelled"
    assert client.patch(f"/api/fees/{fee_id}", headers=admin_headers,
                        json={"amount_due_minor": 5}).status_code == 409


def test_update_fee(client, admin_headers, student):
    fee_id = _fee(client, admin_headers, student).get_json()["data"]["id"]
    _pay(client, admin_headers, fee_id, 300000)
    below = client.patch(f"/api/fees/{fee_id}", headers=admin_headers,
                         json={"amount_due_minor": 200000})
    assert below.get_json()["error"]["code"] == "below_paid"
    ok = client.patch(f"/api/fees/{fee_id}", headers=admin_headers,
                      json={"amount_due_minor": 300000, "description": "Adjusted"})
    assert ok.get_json()["data"]["status"] == "paid"


def test_generate_monthly_rent(client, db, admin_headers, make_student, make_room):
    room = make_room(monthly_fee_minor=450000)
    s1, s2, idle = make_student(), make_student(), make_student()
    db.session.add_all([RoomAllocation(student=s1, room=room, allocated_on=date(2026, 8, 1)),
                        RoomAllocation(student=s2, room=room, allocated_on=date(2026, 8, 1))])
    db.session.commit()
    body = {"month": "2026-11", "due_date": "2026-11-10"}
    res = client.post("/api/fees/generate-rent", headers=admin_headers, json=body)
    assert res.status_code == 201
    assert res.get_json()["data"] == {"created": 2, "skipped": 0, "period": "2026-11"}
    again = client.post("/api/fees/generate-rent", headers=admin_headers, json=body)
    assert again.get_json()["data"]["created"] == 0 and again.get_json()["data"]["skipped"] == 2
    fees = db.session.scalars(db.select(FeeRecord)).all()
    assert {f.student_id for f in fees} == {s1.id, s2.id}
    assert all(f.amount_due_minor == 450000 and f.period_end == date(2026, 11, 30) for f in fees)
    assert idle.id not in {f.student_id for f in fees}
    bad = client.post("/api/fees/generate-rent", headers=admin_headers,
                      json={"month": "2026-13", "due_date": "2026-11-10"})
    assert bad.status_code == 422


def test_students_see_only_their_fees_and_receipts(
        client, admin_headers, student_headers, make_student, db):
    other = make_student()
    db.session.commit()
    mine = _fee(client, admin_headers, student_headers.profile).get_json()["data"]["id"]
    theirs = _fee(client, admin_headers, other).get_json()["data"]["id"]
    my_pay = _pay(client, admin_headers, mine, 1000).get_json()["data"]["id"]
    their_pay = _pay(client, admin_headers, theirs, 1000).get_json()["data"]["id"]

    fees = client.get(f"/api/fees?student_id={other.id}", headers=student_headers).get_json()["data"]
    assert [f["id"] for f in fees["items"]] == [mine]
    assert client.get(f"/api/fees/{theirs}", headers=student_headers).status_code == 404
    pays = client.get("/api/payments", headers=student_headers).get_json()["data"]["items"]
    assert [p["id"] for p in pays] == [my_pay]
    assert client.get(f"/api/payments/{their_pay}/receipt", headers=student_headers).status_code == 404
    receipt = client.get(f"/api/payments/{my_pay}/receipt", headers=student_headers)
    assert receipt.status_code == 200
    body = receipt.get_json()["data"]
    assert body["payment"]["amount_minor"] == 1000
    assert body["student"]["student_code"] == student_headers.profile.student_code
    assert _pay(client, student_headers, mine, 100).status_code == 403


def test_payment_filters(client, admin_headers, student):
    fee_id = _fee(client, admin_headers, student).get_json()["data"]["id"]
    _pay(client, admin_headers, fee_id, 1000, paid_on="2026-09-01")
    upi = _pay(client, admin_headers, fee_id, 2000, method="upi", reference="UPI-1").get_json()["data"]

    def get(qs):
        return client.get(f"/api/payments?{qs}", headers=admin_headers).get_json()["data"]

    assert [p["id"] for p in get("method=upi")["items"]] == [upi["id"]]
    assert len(get("from=2026-09-01&to=2026-09-30")["items"]) == 1
    assert get("")["totals"]["completed_minor"] == 3000
    assert [p["id"] for p in get(f"search={upi['receipt_number']}")["items"]] == [upi["id"]]
