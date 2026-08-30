"""Transactional e-mail (password reset links, project invitations) - stdlib ``smtplib``, no new
dependency. Sends for real only when ``SPECTRE_SMTP_HOST`` is set; otherwise logs the message
(subject + body, which always includes the link) so the app stays usable in a local/dev
environment with no mail server rather than failing the whole request outright. An operator wires
real delivery by setting the ``SPECTRE_SMTP_*`` environment variables - nothing in the code needs
to change.
"""

from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger("spectre.email")


def base_url() -> str:
    """The origin used to build links in e-mails (``SPECTRE_BASE_URL``, e.g.
    ``https://spectre.monlabo.example``). Empty by default - a relative path still explains what
    to do for whoever reads the message (or the dev-mode log line).
    """
    return os.environ.get("SPECTRE_BASE_URL", "").rstrip("/")


def send_email(to: str, subject: str, body: str) -> None:
    host = os.environ.get("SPECTRE_SMTP_HOST")
    if not host:
        logger.warning("SPECTRE_SMTP_HOST non configuré - e-mail non envoyé, contenu ci-dessous :\nÀ : %s\nObjet : %s\n\n%s", to, subject, body)
        return

    port = int(os.environ.get("SPECTRE_SMTP_PORT", "587"))
    username = os.environ.get("SPECTRE_SMTP_USER")
    password = os.environ.get("SPECTRE_SMTP_PASSWORD")
    from_addr = os.environ.get("SPECTRE_SMTP_FROM", username or "spectre@localhost")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = from_addr
    message["To"] = to
    message.set_content(body)

    with smtplib.SMTP(host, port, timeout=10) as server:
        server.starttls()
        if username:
            server.login(username, password or "")
        server.send_message(message)
