"""
sms_test.py — Stage 5a: send ONE test SMS via Twilio (isolated test).

This is a standalone check that Twilio works on its own. It does NOT touch
Gmail, the classifier, or the agent — it just sends a single text from your
Twilio number to your own verified number.

All credentials and phone numbers come from .env (never hardcoded). Numbers
must be in E.164 format: a plus sign, country code, then the number, with no
spaces or dashes (e.g. +12025550123).

Run it with:  python sms_test.py
"""

import os
import sys

from dotenv import load_dotenv
from twilio.rest import Client

load_dotenv()

ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER")
TO_NUMBER = os.environ.get("TWILIO_TO_NUMBER")

BODY = "Test alert from your job-application agent — Twilio is working!"


def main():
    # Make sure every value is present before calling Twilio.
    missing = [
        name
        for name, value in (
            ("TWILIO_ACCOUNT_SID", ACCOUNT_SID),
            ("TWILIO_AUTH_TOKEN", AUTH_TOKEN),
            ("TWILIO_FROM_NUMBER", FROM_NUMBER),
            ("TWILIO_TO_NUMBER", TO_NUMBER),
        )
        if not value
    ]
    if missing:
        print("Missing required .env values: " + ", ".join(missing))
        sys.exit(1)

    client = Client(ACCOUNT_SID, AUTH_TOKEN)

    try:
        message = client.messages.create(
            body=BODY,
            from_=FROM_NUMBER,  # E.164, plus sign preserved
            to=TO_NUMBER,
        )
        print(f"Sent! SID: {message.sid}  status: {message.status}")
    except Exception as exc:
        # Twilio errors are descriptive (unverified number, bad format, bad
        # credentials, ...). Surface the whole thing to help debugging.
        print("Failed to send SMS. Full error below:")
        print(repr(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()
