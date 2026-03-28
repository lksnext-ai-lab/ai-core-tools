"""Transactional email service for SaaS mode.

All methods are no-ops in self-managed mode (is_self_managed() guard).
Initial implementation uses SMTP via smtplib.
"""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from deployment_mode import is_self_managed
from utils.logger import get_logger

logger = get_logger(__name__)


class EmailService:
    """Transactional email sender. All methods are no-ops in self-managed mode."""

    @staticmethod
    def send_verification_email(to: str, token: str) -> None:
        """Send an email verification link to the user."""
        if is_self_managed():
            return

        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
        verify_url = f"{frontend_url}/verify-email?token={token}"
        subject = "Verify your Mattin AI account"
        body_html = f"""
        <p>Welcome to Mattin AI!</p>
        <p>Please verify your email address by clicking the link below:</p>
        <p><a href="{verify_url}">Verify Email</a></p>
        <p>This link expires in 24 hours.</p>
        """
        body_text = f"Verify your email: {verify_url}"
        EmailService._send(to=to, subject=subject, body_html=body_html, body_text=body_text)

    @staticmethod
    def send_password_reset_email(to: str, token: str) -> None:
        """Send a password reset link to the user."""
        if is_self_managed():
            return

        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
        reset_url = f"{frontend_url}/password-reset?token={token}"
        subject = "Reset your Mattin AI password"
        body_html = f"""
        <p>You requested a password reset for your Mattin AI account.</p>
        <p><a href="{reset_url}">Reset Password</a></p>
        <p>This link expires in 1 hour. If you did not request this, ignore this email.</p>
        """
        body_text = f"Reset your password: {reset_url}"
        EmailService._send(to=to, subject=subject, body_html=body_html, body_text=body_text)

    @staticmethod
    def send_quota_warning_email(to: str, pct: float) -> None:
        """Send a system LLM quota warning email when usage reaches 80%."""
        if is_self_managed():
            return

        pct_int = int(pct * 100)
        subject = f"Mattin AI: You've used {pct_int}% of your monthly LLM quota"
        body_html = f"""
        <p>You have used <strong>{pct_int}%</strong> of your monthly system LLM quota.</p>
        <p>To avoid interruptions, consider upgrading your plan.</p>
        """
        body_text = f"You've used {pct_int}% of your monthly system LLM quota."
        EmailService._send(to=to, subject=subject, body_html=body_html, body_text=body_text)

    @staticmethod
    def send_dunning_email(to: str, days_remaining: int) -> None:
        """Send a payment failure dunning email."""
        if is_self_managed():
            return

        subject = "Mattin AI: Action required — payment issue"
        body_html = f"""
        <p>We were unable to process your payment for Mattin AI.</p>
        <p>You have <strong>{days_remaining} day(s)</strong> to update your payment method before your
        subscription is cancelled and your resources are frozen.</p>
        <p>Please update your payment method to avoid disruption.</p>
        """
        body_text = f"Payment failed. {days_remaining} day(s) remaining to update payment method."
        EmailService._send(to=to, subject=subject, body_html=body_html, body_text=body_text)

    # ── Private SMTP send helper ──────────────────────────────────────────────

    @staticmethod
    def _send(to: str, subject: str, body_html: str, body_text: str) -> None:
        """Send an email via SMTP. Logs errors without raising."""
        email_from = os.getenv("EMAIL_FROM", "noreply@mattinai.com")
        smtp_host = os.getenv("SMTP_HOST", "localhost")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.getenv("SMTP_USER", "")
        smtp_pass = os.getenv("SMTP_PASS", "")

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = email_from
            msg["To"] = to
            msg.attach(MIMEText(body_text, "plain"))
            msg.attach(MIMEText(body_html, "html"))

            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.ehlo()
                if smtp_port != 25:
                    server.starttls()
                if smtp_user and smtp_pass:
                    server.login(smtp_user, smtp_pass)
                server.sendmail(email_from, [to], msg.as_string())

            logger.info("Email sent to %s: %s", to, subject)
        except Exception as exc:
            logger.error("Failed to send email to %s: %s", to, exc)
