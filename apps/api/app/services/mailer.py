"""Real SMTP sending for School invite emails (Coordinator-issued Teacher/Principal/
Parent invites). Distinct from `integrations.send_notification`'s generic webhook-
forwarding channel -- that one hands a JSON payload to an external notification service
and stays in place for the rest of the platform's notification traffic. This module is
the first place in the codebase that actually composes and sends an email itself, using
only the Python standard library (`smtplib`/`email`) so no new dependency was needed.

Returns `(status, error)` for every send, same contract as `send_notification`, so
callers persist the outcome the same way regardless of which mechanism sent it. `status`
is one of "not_configured" (no SMTP host set -- a normal, reportable state, not an
error), "sent", or "failed".
"""

import asyncio
import smtplib
from datetime import UTC, datetime
from email.message import EmailMessage
from html import escape

from app.core.config import settings

ROLE_LABELS = {"school_principal": "Principal", "school_teacher": "Teacher", "school_parent": "Parent"}


def _school_invite_html(*, recipient_name: str, role_label: str, school_name: str, accept_url: str, coordinator_name: str, expires_at: datetime) -> str:
    logo_url = f"{settings.frontend_url}/brand/logo-dark.png"
    expires_label = expires_at.strftime("%d %b %Y")
    return f"""<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#f4f7fb;font-family:Segoe UI,Helvetica,Arial,sans-serif;color:#0f2850;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f7fb;padding:32px 0;">
      <tr>
        <td align="center">
          <table role="presentation" width="480" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 18px rgba(15,40,80,.08);">
            <tr>
              <td style="background:#0a1e3f;padding:28px 32px;">
                <img src="{logo_url}" alt="EduSphere" height="40" style="display:block;">
              </td>
            </tr>
            <tr>
              <td style="padding:32px;">
                <h1 style="font-size:20px;margin:0 0 16px;">You're invited to {school_name}</h1>
                <p style="font-size:15px;line-height:1.6;margin:0 0 16px;">Hi {recipient_name},</p>
                <p style="font-size:15px;line-height:1.6;margin:0 0 16px;">
                  {coordinator_name} has invited you to join <strong>{school_name}</strong> on EduSphere as a <strong>{role_label}</strong>.
                </p>
                <table role="presentation" cellpadding="0" cellspacing="0" style="margin:24px 0;">
                  <tr>
                    <td style="border-radius:12px;background:#1554d8;">
                      <a href="{accept_url}" style="display:inline-block;padding:14px 28px;color:#ffffff;font-weight:700;font-size:15px;text-decoration:none;">Accept invite &amp; set your password</a>
                    </td>
                  </tr>
                </table>
                <p style="font-size:13px;line-height:1.6;color:#60738b;margin:0 0 8px;">
                  This link is single-use and expires on {expires_label}. If the button above doesn't work, copy and paste this link into your browser:
                </p>
                <p style="font-size:13px;line-height:1.6;word-break:break-all;margin:0;">
                  <a href="{accept_url}" style="color:#1554d8;">{accept_url}</a>
                </p>
              </td>
            </tr>
            <tr>
              <td style="padding:20px 32px;background:#f8fafc;border-top:1px solid #edf1f6;">
                <p style="font-size:12px;color:#60738b;margin:0;">
                  Sent by {coordinator_name} via EduSphere. Didn't expect this? You can safely ignore this email.
                </p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""


def _school_invite_text(*, recipient_name: str, role_label: str, school_name: str, accept_url: str, coordinator_name: str, expires_at: datetime) -> str:
    expires_label = expires_at.strftime("%d %b %Y")
    return (
        f"Hi {recipient_name},\n\n"
        f"{coordinator_name} has invited you to join {school_name} on EduSphere as a {role_label}.\n\n"
        f"Accept your invite and set your password: {accept_url}\n\n"
        f"This link is single-use and expires on {expires_label}.\n\n"
        f"Didn't expect this? You can safely ignore this email."
    )


def _send_sync(msg: EmailMessage) -> None:
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_username and settings.smtp_password:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(msg)


async def send_school_invite_email(
    *, to_email: str, recipient_name: str, role: str, school_name: str, accept_url: str,
    coordinator_name: str, coordinator_email: str, expires_at: datetime,
) -> tuple[str, str | None]:
    if not settings.smtp_host or not settings.smtp_from_email:
        return "not_configured", None
    role_label = ROLE_LABELS.get(role, role)
    msg = EmailMessage()
    msg["Subject"] = f"You're invited to join {school_name} on EduSphere"
    # The technical From must be the verified SMTP account or providers reject/quarantine
    # the send; the display name and Reply-To are what actually carry "from the
    # Coordinator" for the recipient -- replying goes straight to them.
    msg["From"] = f"{coordinator_name} via EduSphere <{settings.smtp_from_email}>"
    msg["To"] = to_email
    msg["Reply-To"] = f"{coordinator_name} <{coordinator_email}>"
    msg.set_content(_school_invite_text(recipient_name=recipient_name, role_label=role_label, school_name=school_name, accept_url=accept_url, coordinator_name=coordinator_name, expires_at=expires_at))
    msg.add_alternative(
        _school_invite_html(recipient_name=recipient_name, role_label=role_label, school_name=school_name, accept_url=accept_url, coordinator_name=coordinator_name, expires_at=expires_at),
        subtype="html",
    )
    try:
        await asyncio.to_thread(_send_sync, msg)
        return "sent", None
    except Exception as exc:
        return "failed", str(exc)[:500]


# --- SCH-007: Parent Portal notifications -------------------------------------------------

def _parent_notification_html(*, recipient_name: str, school_name: str, title: str, body: str, action_url: str | None) -> str:
    logo_url = f"{settings.frontend_url}/brand/logo-dark.png"
    button = (
        f"""<table role="presentation" cellpadding="0" cellspacing="0" style="margin:24px 0;">
                  <tr>
                    <td style="border-radius:12px;background:#1554d8;">
                      <a href="{action_url}" style="display:inline-block;padding:14px 28px;color:#ffffff;font-weight:700;font-size:15px;text-decoration:none;">Open in EduSphere</a>
                    </td>
                  </tr>
                </table>"""
        if action_url
        else ""
    )
    return f"""<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#f4f7fb;font-family:Segoe UI,Helvetica,Arial,sans-serif;color:#0f2850;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f7fb;padding:32px 0;">
      <tr>
        <td align="center">
          <table role="presentation" width="480" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 18px rgba(15,40,80,.08);">
            <tr>
              <td style="background:#0a1e3f;padding:28px 32px;">
                <img src="{logo_url}" alt="EduSphere" height="40" style="display:block;">
              </td>
            </tr>
            <tr>
              <td style="padding:32px;">
                <h1 style="font-size:20px;margin:0 0 16px;">{title}</h1>
                <p style="font-size:15px;line-height:1.6;margin:0 0 16px;">Hi {recipient_name},</p>
                <p style="font-size:15px;line-height:1.6;margin:0 0 16px;">{body}</p>
                {button}
              </td>
            </tr>
            <tr>
              <td style="padding:20px 32px;background:#f8fafc;border-top:1px solid #edf1f6;">
                <p style="font-size:12px;color:#60738b;margin:0;">
                  Sent by {school_name} via EduSphere. You receive this because you are a linked parent at this school.
                </p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""


async def send_parent_notification_email(*, to_email: str, recipient_name: str, school_name: str, title: str, body: str, action_url: str | None) -> tuple[str, str | None]:
    """SCH-007: the email copy of a Parent Portal notification (in-app row is always written
    first by the caller; this is the delivery channel on top of it, `NOT-001`). Same
    (status, error) contract and same not_configured/sent/failed semantics as the invite
    mailer above -- an unconfigured SMTP host never blocks the write that triggered it."""
    if not settings.smtp_host or not settings.smtp_from_email:
        return "not_configured", None
    msg = EmailMessage()
    msg["Subject"] = f"{title} -- {school_name}"
    msg["From"] = f"{school_name} via EduSphere <{settings.smtp_from_email}>"
    msg["To"] = to_email
    text = f"Hi {recipient_name},\n\n{title}\n\n{body}\n"
    if action_url:
        text += f"\nOpen in EduSphere: {action_url}\n"
    msg.set_content(text)
    msg.add_alternative(_parent_notification_html(recipient_name=recipient_name, school_name=school_name, title=title, body=body, action_url=action_url), subtype="html")
    try:
        await asyncio.to_thread(_send_sync, msg)
        return "sent", None
    except Exception as exc:
        return "failed", str(exc)[:500]


# --- ENH-003 / DEC-SCOPE-019: first-time set-password link for admin-provisioned accounts -------

WELCOME_EXPIRY_HOURS_LABEL = "72 hours"


def _welcome_html(*, recipient_name: str, role_label: str, set_password_url: str, expires_label: str, invited_by_name: str) -> str:
    logo_url = f"{settings.frontend_url}/brand/logo-dark.png"
    name, role, inviter = escape(recipient_name), escape(role_label), escape(invited_by_name)
    url = escape(set_password_url, quote=True)
    return f"""<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#f4f7fb;font-family:Segoe UI,Helvetica,Arial,sans-serif;color:#0f2850;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f7fb;padding:32px 0;">
      <tr>
        <td align="center">
          <table role="presentation" width="480" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 18px rgba(15,40,80,.08);">
            <tr>
              <td style="background:#0a1e3f;padding:28px 32px;">
                <img src="{logo_url}" alt="EduSphere" height="40" style="display:block;">
              </td>
            </tr>
            <tr>
              <td style="padding:32px;">
                <h1 style="font-size:20px;margin:0 0 16px;">Welcome to EduSphere</h1>
                <p style="font-size:15px;line-height:1.6;margin:0 0 16px;">Hi {name},</p>
                <p style="font-size:15px;line-height:1.6;margin:0 0 16px;">
                  {inviter} has created your EduSphere account as <strong>{role}</strong>. Set your password to get started.
                </p>
                <table role="presentation" cellpadding="0" cellspacing="0" style="margin:24px 0;">
                  <tr>
                    <td style="border-radius:12px;background:#1554d8;">
                      <a href="{url}" style="display:inline-block;padding:14px 28px;color:#ffffff;font-weight:700;font-size:15px;text-decoration:none;">Set your password</a>
                    </td>
                  </tr>
                </table>
                <p style="font-size:13px;line-height:1.6;color:#60738b;margin:0 0 8px;">
                  This link is single-use and expires in {WELCOME_EXPIRY_HOURS_LABEL} ({expires_label}). If the button doesn't work, copy and paste this link into your browser:
                </p>
                <p style="font-size:13px;line-height:1.6;word-break:break-all;margin:0;">
                  <a href="{url}" style="color:#1554d8;">{url}</a>
                </p>
              </td>
            </tr>
            <tr>
              <td style="padding:20px 32px;background:#f8fafc;border-top:1px solid #edf1f6;">
                <p style="font-size:12px;color:#60738b;margin:0;">
                  Didn't expect this? You can safely ignore this email.
                </p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""


def _welcome_text(*, recipient_name: str, role_label: str, set_password_url: str, expires_label: str, invited_by_name: str) -> str:
    return (
        f"Hi {recipient_name},\n\n"
        f"{invited_by_name} has created your EduSphere account as {role_label}.\n\n"
        f"Set your password: {set_password_url}\n\n"
        f"This link is single-use and expires in {WELCOME_EXPIRY_HOURS_LABEL} ({expires_label}).\n\n"
        f"Didn't expect this? You can safely ignore this email."
    )


async def send_welcome_email(
    *,
    to_email: str,
    recipient_name: str,
    role: str,
    set_password_url: str,
    expires_at: datetime,
    invited_by_name: str,
) -> tuple[str, str | None]:
    """ENH-003: the first-time set-password email for an admin-provisioned account. Same
    (status, error) contract as the invite mailer: `not_configured` is a normal, reportable
    state that never blocks the account creation that triggered it."""
    if not settings.smtp_host or not settings.smtp_from_email:
        return "not_configured", None
    role_label = ROLE_LABELS.get(role, role.replace("_", " ").title())
    try:
        # Building the message is inside the try on purpose: a malformed address makes EmailMessage
        # raise ValueError, and a send problem must never escape as a 500 after the account committed.
        msg = EmailMessage()
        msg["Subject"] = "Welcome to EduSphere -- set your password"
        msg["From"] = f"EduSphere <{settings.smtp_from_email}>"
        msg["To"] = to_email
        expires_label = expires_at.astimezone(UTC).strftime("%d %b %Y %H:%M UTC")
        fields = dict(recipient_name=recipient_name, role_label=role_label, set_password_url=set_password_url, expires_label=expires_label, invited_by_name=invited_by_name)
        msg.set_content(_welcome_text(**fields))
        msg.add_alternative(_welcome_html(**fields), subtype="html")
        await asyncio.to_thread(_send_sync, msg)
        return "sent", None
    except Exception as exc:
        return "failed", str(exc)[:500]
