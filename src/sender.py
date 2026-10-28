"""
Email sender module.

Handles SMTP sending via Gmail and confirmation emails to the operator.
"""

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib


def send_email(
    to_email: str,
    subject: str,
    html_body: str,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_pass: str,
    from_name: str,
    from_email: str,
) -> bool:
    """
    Send an HTML email via SMTP.

    Returns True on success, False on failure.
    """
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = f"{from_name} <{from_email}>"
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(html_body, "html"))

        server = smtplib.SMTP(smtp_host, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"  SMTP error: {e}")
        return False


def send_confirmation_email(
    sent_count: int,
    total_processed: int,
    daily_limit: int,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_pass: str,
    from_name: str,
    from_email: str,
) -> bool:
    """
    Send a confirmation email to the operator after each run.
    """
    from datetime import datetime, timezone

    subject = f"Lead Outreach Complete - {sent_count} emails sent"
    body = f"""
    Lead Outreach Run Complete
    ==========================
    Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
    Emails sent this run: {sent_count}
    Daily total processed: {total_processed}
    Daily limit: {daily_limit}

    Check leads.db for full details.

    - Andrei's Outreach Bot
    """
    html_body = f"<p>{body.replace(chr(10), '<br>')}</p>"
    return send_email(
        to_email=smtp_user,
        subject=subject,
        html_body=html_body,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_user=smtp_user,
        smtp_pass=smtp_pass,
        from_name=from_name,
        from_email=from_email,
    )
