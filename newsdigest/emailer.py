"""Station six: send the digest through Gmail using an app password."""

import os
import smtplib
from email.message import EmailMessage


def send_email(subject, html, text):
    sender = os.environ.get("GMAIL_ADDRESS", "").strip()
    password = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    recipients = os.environ.get("EMAIL_TO", "").strip() or sender
    if not sender or not password:
        raise RuntimeError("GMAIL_ADDRESS and GMAIL_APP_PASSWORD secrets are not set")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"News Digest <{sender}>"
    msg["To"] = recipients
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=60) as smtp:
        smtp.login(sender, password)
        smtp.send_message(msg)
    print(f"Email sent to {recipients.count(',') + 1} recipient(s)")
