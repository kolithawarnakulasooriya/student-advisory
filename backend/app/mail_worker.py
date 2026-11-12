"""Invitation-only local SMTP worker; no record or general notification authority."""

import argparse
import smtplib
import time
from datetime import timedelta
from email.message import EmailMessage

from sqlalchemy import select, text

from app.config import Settings
from app.db import make_engine, safe_runtime_role, transaction
from app.models import Invitation, OutboxEvent
from app.security import now
from app.staff_security import WORKFLOW_LOCK
from app.staff_services import invitation_token


def deliver_once(cfg: Settings) -> int:
    engine = make_engine(cfg.mail_database_url.get_secret_value())
    processed = 0
    try:
        with transaction(engine) as db:
            if not safe_runtime_role(db, "advisory_mail"):
                raise ValueError("Unsafe mail database role")
            db.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": WORKFLOW_LOCK})
            # Delivery is serialized with authority changes. Local SMTP has a bounded timeout.
            event = db.scalar(
                select(OutboxEvent)
                .where(
                    OutboxEvent.event_type == "invitation.send",
                    OutboxEvent.state == "pending",
                    OutboxEvent.available_at <= now(),
                )
                .order_by(OutboxEvent.occurred_at, OutboxEvent.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if event is None:
                return 0
            inv = db.get(Invitation, event.aggregate_id)
            event.attempts += 1
            if (
                inv is None
                or inv.status != "pending"
                or inv.expires_at <= now()
                or inv.version != event.aggregate_version
                or not db.scalar(text("SELECT inviter_allowed(:id)"), {"id": inv.id})
            ):
                event.state = "cancelled"
                if inv and inv.status == "pending" and inv.expires_at <= now():
                    inv.status = "expired"
                return 1
            token = invitation_token(inv, cfg)
            message = EmailMessage()
            message["From"] = "advisory@local.test"
            message["To"] = inv.email
            message["Subject"] = "Synthetic Student Advisory invitation"
            message["Message-ID"] = f"<{event.id}@advisory.test>"
            message.set_content(
                "Synthetic local invitation. No real student records.\n\n"
                f"Open {cfg.web_origin}/#invitation={token}\n\n"
                "Sign in or register with the invited synthetic email, verify it, then accept.\n"
                "The invitation is single-use and expires. "
                "No privileges activate before acceptance."
            )
            try:
                with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=5) as smtp:
                    smtp.send_message(message)
            except (OSError, smtplib.SMTPException):
                event.last_error = "SMTP_UNAVAILABLE"
                event.available_at = now() + timedelta(
                    seconds=min(300, 2 ** min(event.attempts, 8))
                )
                if event.attempts >= 10:
                    event.state = "failed"
            else:
                event.state = "sent"
                event.last_error = None
            processed = 1
    finally:
        engine.dispose()
    return processed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    cfg = Settings()
    while True:
        processed = deliver_once(cfg)
        if args.once:
            break
        if not processed:
            time.sleep(1)


if __name__ == "__main__":
    main()
