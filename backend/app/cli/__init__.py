"""Custom `flask` CLI commands.

    flask create-admin   Interactively create an administrator account.
    flask ensure-admin   Non-interactive: create the administrator named by the
                         ADMIN_EMAIL / ADMIN_PASSWORD / ADMIN_NAME environment
                         variables if it does not exist yet. Safe to run on every
                         start-up (used by the Render start command, because free
                         Render services have no shell).

The password is read with a hidden prompt (or from the HMS_ADMIN_PASSWORD
environment variable for automated setups) — it is never passed as a
command-line argument, so it does not end up in shell history.
"""
import os

import click
from flask import Flask

from ..extensions import db
from ..models import ApprovalStatus, AuditLog, Role, User
from ..utils.time import utcnow
from ..utils.validators import is_valid_email, password_problems


def _create_admin(email: str, full_name: str, password: str) -> User:
    email = User.normalize_email(email)
    if not is_valid_email(email):
        raise click.BadParameter("Enter a valid email address.", param_hint="email")
    if not full_name.strip():
        raise click.BadParameter("Full name is required.", param_hint="full-name")
    problems = password_problems(password)
    if problems:
        raise click.BadParameter("Password " + "; ".join(problems) + ".", param_hint="password")
    if db.session.scalar(db.select(User).filter_by(email=email)):
        raise click.ClickException(f"A user with email {email} already exists.")

    user = User(email=email, full_name=full_name.strip(), role=Role.ADMIN, is_active=True,
                approval_status=ApprovalStatus.APPROVED, email_verified_at=utcnow(),
                created_via="cli")
    user.set_password(password)
    db.session.add(user)
    db.session.flush()
    db.session.add(AuditLog(actor_id=None, action="user.create_admin", entity_type="user",
                            entity_id=user.id, details={"via": "cli", "email": email}))
    db.session.commit()
    return user


def register_cli(app: Flask) -> None:
    @app.cli.command("create-admin")
    @click.option("--email", prompt="Admin email")
    @click.option("--full-name", prompt="Full name")
    def create_admin_command(email: str, full_name: str):
        """Create an administrator account (prompts for a hidden password)."""
        password = os.environ.get("HMS_ADMIN_PASSWORD")
        if not password:
            password = click.prompt("Password", hide_input=True,
                                    confirmation_prompt="Confirm password")
        user = _create_admin(email, full_name, password)
        click.secho(f"Administrator {user.email} created (id={user.id}).", fg="green")

    @app.cli.command("ensure-admin")
    def ensure_admin_command():
        """Create the admin from ADMIN_EMAIL/ADMIN_PASSWORD if it does not exist."""
        email = User.normalize_email(os.environ.get("ADMIN_EMAIL", ""))
        password = os.environ.get("ADMIN_PASSWORD", "")
        full_name = os.environ.get("ADMIN_NAME", "").strip() or "Administrator"
        if not email:
            click.echo("ensure-admin: ADMIN_EMAIL is not set; skipping.")
            return
        existing = db.session.scalar(db.select(User).filter_by(email=email))
        if existing is not None:
            if existing.role == Role.ADMIN:
                click.echo(f"ensure-admin: administrator {email} already exists.")
            else:
                # Never silently promote someone else's account.
                click.secho(f"ensure-admin: {email} belongs to a non-admin account; "
                            "not changed. Choose a different ADMIN_EMAIL.", fg="yellow")
            return
        if not password:
            raise click.ClickException("ADMIN_PASSWORD must be set to create the administrator.")
        user = _create_admin(email, full_name, password)
        click.secho(f"ensure-admin: administrator {user.email} created (id={user.id}).", fg="green")
