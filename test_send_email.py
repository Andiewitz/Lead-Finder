#!/usr/bin/env python3
"""
Send a test email to galletoandre94@gmail.com to verify the setup works.
Uses the same send_email function as main.py.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(".env")

from main import send_email, FROM_NAME, FROM_EMAIL, FROM_COMPANY, VALUE_PROP

TEST_EMAIL = "galletoandre94@gmail.com"

subject = f"Test email from {FROM_NAME}"

html_body = f"""
<h2>Test Email</h2>
<p>Hi Andrei,</p>
<p>This is a test email from your lead outreach automation system.</p>
<p><strong>From:</strong> {FROM_NAME}</p>
<p><strong>Company:</strong> {FROM_COMPANY}</p>
<p><strong>Value Prop:</strong> {VALUE_PROP}</p>
<p>If you received this, your Gmail SMTP is working correctly!</p>
<p>Best,<br>{FROM_NAME}</p>
"""

print(f"Sending test email to {TEST_EMAIL}...")
print(f"From: {FROM_NAME} <{FROM_EMAIL}>")
print(f"Subject: {subject}")

success = send_email(TEST_EMAIL, subject, html_body)

if success:
    print("✅ Test email sent successfully!")
else:
    print("❌ Test email failed to send.")
    sys.exit(1)
