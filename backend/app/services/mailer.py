"""Outgoing email.

Backends (MAIL_BACKEND):
* smtp   - real delivery through MAIL_SERVER, sent on a background thread so a
           request's response time does not reveal whether an email was sent.
* brevo  - real delivery through Brevo's HTTPS API (free plan: 300 emails/day),
           also on a background thread. Use this where outgoing SMTP ports are
           blocked, e.g. Render's free web services.
* file   - DEVELOPMENT ONLY. Each email is written to backend/instance/dev-outbox/
           as a .txt file you can open to click verification / reset links.
           Refused in production by config.get_config().
* memory - tests. Messages are appended to app.extensions["mail_outbox"].

Email bodies may contain one-time links, so they are never written to the
application log. Delivery failures are logged without recipients' tokens.
"""
from html import escape
import json
import smtplib
import ssl
import threading
from datetime import datetime
from email.message import EmailMessage
from email.utils import parseaddr
from pathlib import Path
from urllib import error as urlerror
from urllib import request as urlrequest

from flask import current_app


def _build(to: str, subject: str, text: str, html: str | None) -> EmailMessage:
    cfg = current_app.config
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["MAIL_DEFAULT_SENDER"] or f"{cfg['HOSTEL_NAME']} <no-reply@localhost>"
    msg["To"] = to
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    return msg


def smtp_configured(app=None) -> bool:
    cfg = (app or current_app).config
    return bool(cfg["MAIL_SERVER"] and cfg["MAIL_DEFAULT_SENDER"])


def brevo_configured(app=None) -> bool:
    cfg = (app or current_app).config
    return bool(cfg["BREVO_API_KEY"] and cfg["MAIL_DEFAULT_SENDER"])


def _brevo_payload(msg: EmailMessage) -> dict:
    sender_name, sender_email = parseaddr(msg["From"])
    to_name, to_email = parseaddr(msg["To"])
    payload = {
        "sender": {"email": sender_email, **({"name": sender_name} if sender_name else {})},
        "to": [{"email": to_email, **({"name": to_name} if to_name else {})}],
        "subject": str(msg["Subject"]),
        "textContent": msg.get_body(preferencelist=("plain",)).get_content(),
    }
    html_part = msg.get_body(preferencelist=("html",))
    if html_part is not None:
        payload["htmlContent"] = html_part.get_content()
    return payload


def _send_brevo(app, msg: EmailMessage) -> None:
    cfg = app.config
    req = urlrequest.Request(
        cfg["BREVO_API_URL"],
        data=json.dumps(_brevo_payload(msg)).encode("utf-8"),
        method="POST",
        headers={"api-key": cfg["BREVO_API_KEY"], "accept": "application/json",
                 "content-type": "application/json"},
    )
    try:
        with urlrequest.urlopen(req, timeout=cfg["MAIL_TIMEOUT_SECONDS"]) as resp:
            resp.read()
    except urlerror.HTTPError as exc:
        # Brevo explains the problem (bad key, unverified sender...) in the body.
        detail = exc.read()[:300].decode("utf-8", "replace")
        app.logger.error("Email delivery failed (Brevo HTTP %s: %s). Subject=%r",
                         exc.code, detail, msg["Subject"])
    except Exception as exc:  # never crash a request because email failed
        app.logger.error("Email delivery failed (%s: %s). Subject=%r",
                         type(exc).__name__, exc, msg["Subject"])


def _send_smtp(app, msg: EmailMessage) -> None:
    cfg = app.config
    try:
        if cfg["MAIL_USE_SSL"]:
            server = smtplib.SMTP_SSL(cfg["MAIL_SERVER"], cfg["MAIL_PORT"],
                                      timeout=cfg["MAIL_TIMEOUT_SECONDS"],
                                      context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(cfg["MAIL_SERVER"], cfg["MAIL_PORT"],
                                  timeout=cfg["MAIL_TIMEOUT_SECONDS"])
        with server:
            if cfg["MAIL_USE_TLS"] and not cfg["MAIL_USE_SSL"]:
                server.starttls(context=ssl.create_default_context())
            if cfg["MAIL_USERNAME"]:
                server.login(cfg["MAIL_USERNAME"], cfg["MAIL_PASSWORD"])
            server.send_message(msg)
    except Exception as exc:  # never crash a request because email failed
        app.logger.error("Email delivery failed (%s: %s). Subject=%r",
                         type(exc).__name__, exc, msg["Subject"])


def _write_outbox(app, msg: EmailMessage) -> Path:
    outbox = Path(app.instance_path) / "dev-outbox"
    outbox.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    safe_to = "".join(c if c.isalnum() else "_" for c in msg["To"])[:60]
    path = outbox / f"{stamp}_{safe_to}.txt"
    body = msg.get_body(preferencelist=("plain",)).get_content()
    path.write_text(
        f"From: {msg['From']}\nTo: {msg['To']}\nSubject: {msg['Subject']}\n\n{body}",
        encoding="utf-8",
    )
    return path


def send_email(to: str, subject: str, text: str, html: str | None = None) -> None:
    app = current_app._get_current_object()
    msg = _build(to, subject, text, html)
    backend = app.config["MAIL_BACKEND"]

    if backend == "memory":
        app.extensions.setdefault("mail_outbox", []).append(msg)
        return
    if backend == "file":
        _write_outbox(app, msg)
        app.logger.info("Development email written to instance/dev-outbox/ (subject %r).",
                        msg["Subject"])
        return
    if backend == "smtp":
        if not smtp_configured(app):
            # Administrators see this in the server log; users get the normal
            # generic response, so nothing sensitive is revealed to them.
            app.logger.error("Email delivery is not configured: set MAIL_SERVER and "
                             "MAIL_DEFAULT_SENDER (see .env.example). Email %r was not sent.",
                             msg["Subject"])
            return
        threading.Thread(target=_send_smtp, args=(app, msg), daemon=True).start()
        return
    if backend == "brevo":
        if not brevo_configured(app):
            app.logger.error("Email delivery is not configured: set BREVO_API_KEY and "
                             "MAIL_DEFAULT_SENDER (see .env.example). Email %r was not sent.",
                             msg["Subject"])
            return
        threading.Thread(target=_send_brevo, args=(app, msg), daemon=True).start()
        return
    app.logger.error("Unknown MAIL_BACKEND %r; email %r was not sent.", backend, msg["Subject"])


# --- templates ---------------------------------------------------------------

def _wrap_html(title: str, paragraphs: list[str], button_text: str, url: str, footer: str) -> str:
    paras = "".join(f'<p style="margin:0 0 14px;color:#334155;font-size:14px;line-height:1.6">{p}</p>'
                    for p in paragraphs)
    return f"""<!doctype html><html><body style="margin:0;background:#f6f7f9;font-family:Segoe UI,Arial,sans-serif">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:32px 16px">
<table role="presentation" width="100%" style="max-width:520px;background:#fff;border:1px solid #e2e8f0;border-radius:12px">
<tr><td style="padding:28px">
<p style="margin:0 0 18px;font-weight:600;color:#16244a;font-size:16px">{escape(current_app.config['HOSTEL_NAME'])}</p>
<h1 style="margin:0 0 16px;font-size:20px;color:#16244a">{title}</h1>{paras}
<p style="margin:22px 0"><a href="{url}" style="background:#1e3160;color:#fff;text-decoration:none;padding:11px 18px;border-radius:8px;font-size:14px;font-weight:600;display:inline-block">{button_text}</a></p>
<p style="margin:0;color:#64748b;font-size:12px;line-height:1.5">If the button does not work, copy this link into your browser:<br>
<span style="word-break:break-all">{url}</span></p>
<p style="margin:18px 0 0;color:#94a3b8;font-size:12px">{footer}</p>
</td></tr></table></td></tr></table></body></html>"""


def send_verification_email(user, raw_token: str) -> None:
    cfg = current_app.config
    url = f"{cfg['FRONTEND_URL']}/verify-email?token={raw_token}"
    hours = cfg["EMAIL_VERIFICATION_TTL_HOURS"]
    text = (f"Hello {user.full_name},\n\nPlease confirm your email address for your "
            f"{cfg['HOSTEL_NAME']} account by opening this link:\n\n{url}\n\n"
            f"The link expires in {hours} hours and can be used once.\n"
            "If you did not create this account, you can ignore this email.\n")
    html = _wrap_html("Confirm your email address",
                      [f"Hello {escape(user.full_name)},",
                       "Please confirm your email address to finish setting up your account."],
                      "Verify email", url,
                      f"This link expires in {hours} hours and can be used once. "
                      "If you did not create this account, ignore this email.")
    send_email(user.email, "Verify your email address", text, html)


def send_password_reset_email(user, raw_token: str) -> None:
    cfg = current_app.config
    url = f"{cfg['FRONTEND_URL']}/reset-password?token={raw_token}"
    minutes = cfg["PASSWORD_RESET_TTL_MINUTES"]
    text = (f"Hello {user.full_name},\n\nA password reset was requested for your "
            f"{cfg['HOSTEL_NAME']} account. Open this link to choose a new password:\n\n{url}\n\n"
            f"The link expires in {minutes} minutes and can be used once.\n"
            "If you did not request this, ignore this email; your password will not change.\n")
    html = _wrap_html("Reset your password",
                      [f"Hello {escape(user.full_name)},",
                       "We received a request to reset your password. Choose a new one below."],
                      "Choose a new password", url,
                      f"This link expires in {minutes} minutes and can be used once. "
                      "If you did not request it, ignore this email.")
    send_email(user.email, "Reset your password", text, html)


def send_staff_invitation_email(invitation, raw_code: str) -> None:
    cfg = current_app.config
    url = f"{cfg['FRONTEND_URL']}/signup?type=staff&code={raw_code}"
    text = (f"Hello,\n\nYou have been invited to join {cfg['HOSTEL_NAME']} as "
            f"{invitation.role}. Create your account here:\n\n{url}\n\n"
            f"Invitation code: {raw_code}\n\nThis invitation is for {invitation.email} only, "
            "can be used once, and expires on "
            f"{invitation.expires_at:%d %b %Y %H:%M} UTC.\n")
    html = _wrap_html("You're invited",
                      [f"You have been invited to join {cfg['HOSTEL_NAME']} as "
                       f"<strong>{invitation.role}</strong>.",
                       f"Your invitation code is <strong>{raw_code}</strong>."],
                      "Create your account", url,
                      f"For {escape(invitation.email)} only. Single use. Expires "
                      f"{invitation.expires_at:%d %b %Y %H:%M} UTC.")
    send_email(invitation.email, f"Invitation to join {cfg['HOSTEL_NAME']}", text, html)


def send_account_decision_email(user, approved: bool, reason: str | None = None) -> None:
    cfg = current_app.config
    if approved:
        url = f"{cfg['FRONTEND_URL']}/login"
        subject = "Your account has been approved"
        text = (f"Hello {user.full_name},\n\nYour {cfg['HOSTEL_NAME']} account has been approved. "
                f"You can now sign in:\n\n{url}\n")
        html = _wrap_html("Your account is approved",
                          [f"Hello {escape(user.full_name)},", "Your account has been approved. You can sign in now."],
                          "Sign in", url, "Welcome aboard.")
    else:
        url = cfg["FRONTEND_URL"]
        subject = "Update on your account registration"
        text = (f"Hello {user.full_name},\n\nYour {cfg['HOSTEL_NAME']} registration was not approved."
                + (f"\nReason: {reason}" if reason else "") + "\nPlease contact the hostel office.\n")
        html = _wrap_html("Registration not approved",
                          [f"Hello {escape(user.full_name)},", "Your registration was not approved."]
                          + ([f"Reason: {reason}"] if reason else []),
                          "Visit the portal", url, "Please contact the hostel office for help.")
    send_email(user.email, subject, text, html)
