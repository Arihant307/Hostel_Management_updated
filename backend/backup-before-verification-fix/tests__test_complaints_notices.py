"""Complaint submission, privacy and resolution; notice publishing and visibility."""
from datetime import date, timedelta

from app.models import AuditLog, RoomAllocation
from app.utils.time import utcnow

COMPLAINT = {"category": "plumbing", "title": "Leaking tap",
             "description": "The bathroom tap has been leaking since Monday."}


def _file(client, headers, **overrides):
    return client.post("/api/complaints", headers=headers, json={**COMPLAINT, **overrides})


# --- complaints ------------------------------------------------------------

def test_student_files_complaint_linked_to_room(client, db, student_headers, make_room):
    room = make_room()
    db.session.add(RoomAllocation(student=student_headers.profile, room=room,
                                  allocated_on=date(2026, 8, 1)))
    db.session.commit()
    res = _file(client, student_headers, priority="high")
    assert res.status_code == 201, res.get_json()
    data = res.get_json()["data"]
    assert (data["status"], data["priority"], data["room"]["id"]) == ("open", "high", room.id)


def test_complaint_validation(client, student_headers):
    res = _file(client, student_headers, category="noise", title="", description="short")
    assert res.status_code == 422
    assert set(res.get_json()["error"]["details"]["fields"]) == {"category", "title", "description"}


def test_staff_cannot_file_complaints(client, warden_headers):
    assert _file(client, warden_headers).status_code == 403


def test_students_only_see_own_complaints(client, db, student_headers, make_student, auth_headers):
    other = make_student()
    other_headers = auth_headers(other.user)
    mine = _file(client, student_headers).get_json()["data"]["id"]
    theirs = _file(client, other_headers).get_json()["data"]["id"]
    items = client.get("/api/complaints", headers=student_headers).get_json()["data"]["items"]
    assert [c["id"] for c in items] == [mine]
    assert client.get(f"/api/complaints/{theirs}", headers=student_headers).status_code == 404
    assert client.post(f"/api/complaints/{theirs}/comments", headers=student_headers,
                       json={"body": "hi"}).status_code == 404


def test_students_cannot_update_status(client, student_headers):
    cid = _file(client, student_headers).get_json()["data"]["id"]
    assert client.patch(f"/api/complaints/{cid}", headers=student_headers,
                        json={"status": "resolved", "resolution": "x"}).status_code == 403


def test_resolution_workflow(client, db, student_headers, warden_headers):
    cid = _file(client, student_headers).get_json()["data"]["id"]
    progress = client.patch(f"/api/complaints/{cid}", headers=warden_headers,
                            json={"status": "in_progress", "assigned_to": "Ramesh (Plumber)"})
    assert progress.status_code == 200
    assert progress.get_json()["data"]["assigned_to"] == "Ramesh (Plumber)"

    no_resolution = client.patch(f"/api/complaints/{cid}", headers=warden_headers,
                                 json={"status": "resolved"})
    assert no_resolution.status_code == 422

    done = client.patch(f"/api/complaints/{cid}", headers=warden_headers,
                        json={"status": "resolved", "resolution": "Washer replaced."})
    data = done.get_json()["data"]
    assert data["status"] == "resolved" and data["resolved_at"]

    reopened = client.patch(f"/api/complaints/{cid}", headers=warden_headers,
                            json={"status": "open"}).get_json()["data"]
    assert reopened["resolved_at"] is None
    assert db.session.scalar(db.select(AuditLog).filter_by(action="complaint.update"))


def test_internal_notes_hidden_from_students(client, student_headers, warden_headers):
    cid = _file(client, student_headers).get_json()["data"]["id"]
    client.post(f"/api/complaints/{cid}/comments", headers=warden_headers,
                json={"body": "Plumber visiting tomorrow."})
    client.post(f"/api/complaints/{cid}/comments", headers=warden_headers,
                json={"body": "Vendor invoice pending.", "is_internal": True})
    reply = client.post(f"/api/complaints/{cid}/comments", headers=student_headers,
                        json={"body": "Thank you!"})
    assert reply.status_code == 201
    student_view = client.get(f"/api/complaints/{cid}", headers=student_headers).get_json()["data"]
    assert [c["body"] for c in student_view["comments"]] == ["Plumber visiting tomorrow.", "Thank you!"]
    staff_view = client.get(f"/api/complaints/{cid}", headers=warden_headers).get_json()["data"]
    assert len(staff_view["comments"]) == 3
    assert client.post(f"/api/complaints/{cid}/comments", headers=student_headers,
                       json={"body": "sneaky", "is_internal": True}).status_code == 403


def test_complaint_filters(client, student_headers, warden_headers):
    a = _file(client, student_headers).get_json()["data"]["id"]
    b = _file(client, student_headers, category="electrical", title="Fan broken",
              description="Ceiling fan does not turn on.").get_json()["data"]["id"]
    client.patch(f"/api/complaints/{b}", headers=warden_headers,
                 json={"status": "rejected", "resolution": "Duplicate of another request."})

    def ids(qs):
        return [c["id"] for c in client.get(f"/api/complaints?{qs}", headers=warden_headers)
                .get_json()["data"]["items"]]

    assert ids("category=electrical") == [b]
    assert ids("status=active") == [a]
    assert ids("status=rejected") == [b]
    assert ids("search=fan") == [b]
    today = date.today().isoformat()
    assert sorted(ids(f"from={today}&to={today}")) == sorted([a, b])
    assert client.get("/api/complaints?status=bogus", headers=warden_headers).status_code == 422


# --- notices ---------------------------------------------------------------

def _notice(client, headers, **overrides):
    body = {"title": "Water supply maintenance", "body": "No water 10am–2pm on Saturday.",
            "category": "maintenance", **overrides}
    return client.post("/api/notices", headers=headers, json=body)


def test_staff_publish_notices(client, warden_headers, admin_headers):
    res = _notice(client, warden_headers, is_pinned=True)
    assert res.status_code == 201, res.get_json()
    data = res.get_json()["data"]
    assert data["is_active"] and data["is_pinned"] and data["created_by"] == "Warden User"
    assert _notice(client, admin_headers).status_code == 201


def test_students_cannot_publish(client, student_headers):
    assert _notice(client, student_headers).status_code == 403


def test_notice_validation(client, admin_headers):
    now = utcnow()
    bad = _notice(client, admin_headers, title="", category="gossip",
                  publish_at=now.isoformat(), expires_at=(now - timedelta(days=1)).isoformat())
    assert bad.status_code == 422
    assert set(bad.get_json()["error"]["details"]["fields"]) == {"title", "category", "expires_at"}
    assert _notice(client, admin_headers, publish_at="not-a-date").status_code == 422


def test_student_visibility(client, admin_headers, student_headers):
    now = utcnow()
    live = _notice(client, admin_headers, title="Live notice").get_json()["data"]["id"]
    pinned = _notice(client, admin_headers, title="Pinned notice", is_pinned=True).get_json()["data"]["id"]
    scheduled = _notice(client, admin_headers, title="Future notice",
                        publish_at=(now + timedelta(days=2)).isoformat() + "Z").get_json()["data"]["id"]
    expired = _notice(client, admin_headers, title="Old notice",
                      publish_at=(now - timedelta(days=10)).isoformat(),
                      expires_at=(now - timedelta(days=1)).isoformat()).get_json()["data"]["id"]
    staff_only = _notice(client, admin_headers, title="Staff meeting",
                         audience="staff").get_json()["data"]["id"]

    items = client.get("/api/notices", headers=student_headers).get_json()["data"]["items"]
    assert [n["id"] for n in items] == [pinned, live]  # pinned first
    for hidden in (scheduled, expired, staff_only):
        assert client.get(f"/api/notices/{hidden}", headers=student_headers).status_code == 404

    def staff_ids(qs):
        return {n["id"] for n in client.get(f"/api/notices?{qs}", headers=admin_headers)
                .get_json()["data"]["items"]}

    assert staff_ids("") == {live, pinned, scheduled, expired, staff_only}
    assert staff_ids("state=scheduled") == {scheduled}
    assert staff_ids("state=expired") == {expired}


def test_update_and_delete_notice(client, db, admin_headers, warden_headers):
    nid = _notice(client, admin_headers).get_json()["data"]["id"]
    res = client.patch(f"/api/notices/{nid}", headers=warden_headers,
                       json={"title": "Updated title", "is_pinned": True})
    assert res.get_json()["data"]["title"] == "Updated title"
    assert client.delete(f"/api/notices/{nid}", headers=warden_headers).status_code == 200
    assert client.get(f"/api/notices/{nid}", headers=admin_headers).status_code == 404
    assert db.session.scalar(db.select(AuditLog).filter_by(action="notice.delete"))
