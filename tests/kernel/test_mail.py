"""Sans SMTP, un e-mail n'est pas envoyé mais journalisé - sans son corps, qui porte un lien secret
(réinitialisation, invitation), sauf sur un poste de développement (``SPECTRE_EMAIL_DEBUG=1``)."""

from __future__ import annotations

from spectre.kernel import mail

BODY = "Ouvrez ce lien : /reinitialiser?token=secret-token"


def _logged(caplog) -> str:
    return "\n".join(record.getMessage() for record in caplog.records)


def test_without_smtp_only_the_recipient_and_subject_are_logged(caplog, monkeypatch):
    monkeypatch.delenv("SPECTRE_EMAIL_DEBUG", raising=False)
    with caplog.at_level("WARNING", logger="spectre.email"):
        mail.send_email("someone@example.com", "Réinitialiser votre mot de passe", BODY)
    logged = _logged(caplog)
    assert "someone@example.com" in logged and "Réinitialiser votre mot de passe" in logged
    assert "secret-token" not in logged


def test_email_debug_logs_the_body(caplog, monkeypatch):
    monkeypatch.setenv("SPECTRE_EMAIL_DEBUG", "1")
    with caplog.at_level("WARNING", logger="spectre.email"):
        mail.send_email("someone@example.com", "Objet", BODY)
    assert "/reinitialiser?token=secret-token" in _logged(caplog)
