"""
gmail_test.py — Stage 1: Gmail OAuth read-only smoke test.

This script authenticates to the Gmail API using OAuth 2.0 and prints the
subject line and sender of your 10 most recent emails. It does nothing else.

------------------------------------------------------------------------------
HOW THE OAUTH FLOW WORKS
------------------------------------------------------------------------------
OAuth 2.0 lets this script access your Gmail WITHOUT ever seeing your password.
Instead, Google issues short-lived tokens that represent your granted consent.

The pieces involved:

  * credentials.json — the "client secret" file you download from the Google
    Cloud Console. It identifies THIS APPLICATION to Google (not you). It does
    NOT grant any access on its own; it's just the app's ID badge.

  * token.json — created AFTER you grant access. It holds the access token
    (short-lived) and a refresh token (long-lived) that represent YOUR consent
    for this app. This is the file that actually grants Gmail access, which is
    why it must be kept secret and is git-ignored.

  * SCOPES — the exact permissions the app is asking for. Here we request ONLY
    gmail.readonly, so even if the token leaked, it could not send or delete
    mail — only read it.

The flow, step by step:

  1. On first run there is no token.json, so the script starts the
     "installed app" OAuth flow: it opens your browser to a Google consent
     screen showing exactly which permissions (read-only Gmail) are requested.

  2. You log in and click "Allow". Google redirects back to a tiny local web
     server this script spins up, handing it an authorization code.

  3. The script exchanges that code for an access token + refresh token and
     saves both to token.json. Future runs reuse this file — no browser needed.

  4. On later runs, if the access token has expired, the saved refresh token
     is used to silently obtain a fresh access token (still no browser).
------------------------------------------------------------------------------
"""

import os.path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# READ-ONLY scope only. If you ever change this list, delete token.json so the
# consent screen runs again with the new permissions.
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def get_credentials():
    """Return valid Gmail API credentials, running the OAuth flow if needed."""
    creds = None

    # Step 4 (fast path): reuse a previously saved token if it exists.
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    # If we have no valid credentials, either refresh them or run the full flow.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            # Access token expired but we have a refresh token: renew silently.
            creds.refresh(Request())
        else:
            # Steps 1–3: no usable token, so launch the browser consent flow.
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Persist the (new or refreshed) token for next time.
        with open("token.json", "w", encoding="utf-8") as token_file:
            token_file.write(creds.to_json())

    return creds


def main():
    creds = get_credentials()

    # Build the Gmail API client using our authorized credentials.
    service = build("gmail", "v1", credentials=creds)

    # Ask for the 10 most recent message IDs in the mailbox. The list call
    # returns only IDs/thread IDs, so we fetch each message's headers next.
    results = (
        service.users()
        .messages()
        .list(userId="me", maxResults=10)
        .execute()
    )
    messages = results.get("messages", [])

    if not messages:
        print("No messages found.")
        return

    for item in messages:
        # Fetch only the Subject and From headers (metadata) to stay minimal
        # and avoid downloading full message bodies.
        msg = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=item["id"],
                format="metadata",
                metadataHeaders=["Subject", "From"],
            )
            .execute()
        )

        headers = msg.get("payload", {}).get("headers", [])
        subject = next(
            (h["value"] for h in headers if h["name"] == "Subject"), "(no subject)"
        )
        sender = next(
            (h["value"] for h in headers if h["name"] == "From"), "(unknown sender)"
        )

        print(f"From:    {sender}")
        print(f"Subject: {subject}")
        print("-" * 60)


if __name__ == "__main__":
    main()
