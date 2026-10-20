"""Cross-cutting checks: every API endpoint (except public ones) requires auth."""
import re

PUBLIC = {
    ("GET", "/api/health"), ("POST", "/api/auth/login"), ("GET", "/api/auth/signup-policy"),
    ("POST", "/api/auth/signup/student"), ("POST", "/api/auth/signup/staff"),
    ("POST", "/api/auth/invitations/validate"), ("POST", "/api/auth/verify-email"),
    ("POST", "/api/auth/resend-verification"), ("POST", "/api/auth/forgot-password"),
    ("POST", "/api/auth/reset-password"),
}


def _endpoints(app):
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith("/api/"):
            continue
        url = re.sub(r"<(?:int:)?[^>]+>", "1", rule.rule)
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            yield method, rule.rule, url


def test_every_endpoint_requires_authentication(app, client):
    checked = 0
    for method, rule, url in _endpoints(app):
        if (method, rule) in PUBLIC:
            continue
        res = client.open(url, method=method, json={})
        assert res.status_code == 401, f"{method} {rule} returned {res.status_code}"
        checked += 1
    assert checked > 40  # sanity: the whole API was scanned


def test_garbage_token_rejected_everywhere(app, client):
    headers = {"Authorization": "Bearer abc.def.ghi"}
    for method, rule, url in _endpoints(app):
        if (method, rule) in PUBLIC:
            continue
        assert client.open(url, method=method, json={}, headers=headers).status_code == 401, rule


def test_error_responses_never_leak_internals(client, admin_headers):
    res = client.post("/api/rooms", headers=admin_headers, data="{not json",
                      content_type="application/json")
    body = res.get_json()
    assert res.status_code == 422 and body["success"] is False
    assert "Traceback" not in res.get_data(as_text=True)
