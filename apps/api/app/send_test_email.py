"""ENH-032 / DEC-SCOPE-225: send one plain "EduSphere test email" through the configured email transport
(SMTP or the Zoho Mail API) to confirm delivery after a setup or a credential change. Prints the transport and
the outcome only -- never a setting value.

Usage (inside the api container):

    docker compose exec api python -m app.send_test_email --to you@example.com

Exit code: 0 sent, 1 failed, 2 not configured.
"""

import argparse
import asyncio
import sys

from app.core.config import settings
from app.services import mailer


def _transport_label() -> str:
    return "Zoho Mail API" if settings.email_transport == "zoho_api" else "SMTP"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Send one EduSphere test email through the configured transport.")
    parser.add_argument("--to", required=True, help="recipient address")
    args = parser.parse_args(argv)
    label = _transport_label()
    status, error = asyncio.run(
        mailer.send_generic_notification_email(
            to_email=args.to,
            recipient_name="EduSphere admin",
            title="EduSphere test email",
            body="This is a test email from EduSphere. If you can read it, email delivery is working.",
            action_url=None,
        )
    )
    if status == "sent":
        print(f"Transport: {label}. Status: sent to {args.to}.")
        return 0
    if status == "not_configured":
        print(f"Transport: {label}. Status: not configured -- set the email settings (see docs/architecture/DEPLOYMENT.md).")
        return 2
    print(f"Transport: {label}. Status: failed -- {error}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
