"""Email sender abstraction for LOCAL auth mode."""

from services.email.sender import (
    EmailSender,
    NoopEmailSender,
    SmtpEmailSender,
    get_email_sender,
    smtp_configured,
)

__all__ = [
    "EmailSender",
    "NoopEmailSender",
    "SmtpEmailSender",
    "get_email_sender",
    "smtp_configured",
]
