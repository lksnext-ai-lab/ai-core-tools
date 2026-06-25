"""EmailSender implementations for LOCAL auth mode.

``NoopEmailSender`` is used when SMTP is not configured — never logs token values.
``SmtpEmailSender`` requires ``SMTP_HOST`` and ``SMTP_FROM``; raises at construction
if absent.  ``get_email_sender()`` is the application-wide factory.

Env vars: SMTP_HOST, SMTP_PORT (587), SMTP_USER, SMTP_PASSWORD, SMTP_TLS (true),
SMTP_FROM, SMTP_TIMEOUT_SECONDS (10).
"""

import os
import smtplib
from abc import ABC, abstractmethod
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from utils.logger import get_logger

logger = get_logger(__name__)



class EmailSender(ABC):
    """Abstract email sender."""

    @abstractmethod
    def send(self, *, to: str, subject: str, body_html: str, body_text: str = "") -> None:
        ...


class NoopEmailSender(EmailSender):
    """Silent sender for deployments without SMTP.  Never logs token or link values."""

    def send(self, *, to: str, subject: str, body_html: str, body_text: str = "") -> None:
        logger.info(
            "auth:email_skipped to=%s subject=%r reason=smtp_not_configured "
            "(link returned directly to admin caller)",
            to,
            subject,
        )



class SmtpEmailSender(EmailSender):
    """Outbound email via stdlib smtplib.  Raises ``RuntimeError`` at construction
    if ``SMTP_HOST`` or ``SMTP_FROM`` are absent.
    """

    def __init__(self) -> None:
        self._host: str = os.environ["SMTP_HOST"]
        self._port: int = int(os.getenv("SMTP_PORT", "587"))
        self._user: str = os.getenv("SMTP_USER", "")
        self._password: str = os.getenv("SMTP_PASSWORD", "")
        self._tls: bool = os.getenv("SMTP_TLS", "true").lower() in ("true", "1", "yes")
        self._from: str = os.environ["SMTP_FROM"]
        self._timeout: int = int(os.getenv("SMTP_TIMEOUT_SECONDS", "10"))

    def send(self, *, to: str, subject: str, body_html: str, body_text: str = "") -> None:
        """Send via SMTP.  Auth/connect errors re-raise; transient errors are logged only."""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self._from
        msg["To"] = to

        if body_text:
            msg.attach(MIMEText(body_text, "plain"))
        msg.attach(MIMEText(body_html, "html"))

        try:
            with smtplib.SMTP(self._host, self._port, timeout=self._timeout) as server:
                server.ehlo()
                if self._tls:
                    server.starttls()
                if self._user and self._password:
                    server.login(self._user, self._password)
                server.sendmail(self._from, [to], msg.as_string())

            logger.info("auth:email_sent to=%s subject=%r", to, subject)

        except (smtplib.SMTPAuthenticationError, smtplib.SMTPConnectError):
            logger.error("auth:email_misconfigured to=%s subject=%r", to, subject)
            raise
        except Exception as exc:
            logger.error("auth:email_failed to=%s subject=%r error=%s", to, subject, exc)



def smtp_configured() -> bool:
    """Return True when both SMTP_HOST and SMTP_FROM are set."""
    return bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_FROM"))


def get_email_sender() -> EmailSender:
    """Return ``SmtpEmailSender`` when SMTP is configured, otherwise ``NoopEmailSender``."""
    if smtp_configured():
        return SmtpEmailSender()
    return NoopEmailSender()
