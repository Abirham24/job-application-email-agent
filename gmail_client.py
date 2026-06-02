"""
gmail_client.py — Shared Gmail auth + fetch helpers (READ-ONLY).

Extracted from the Stage 1 test script so the OAuth logic lives in one place.
Used by both gmail_test.py (Stage 1) and classify_inbox.py (Stage 3).

Scope is gmail.readonly ONLY — this module cannot send or delete mail.
"""

import base64
import datetime
import os.path
import re
from html.parser import HTMLParser

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Scopes this app requests. Gmail stays READ-ONLY; we add the Sheets scope so
# we can read (and later write) the tracker spreadsheet.
#
# NOTE on re-authentication: an OAuth token is bound to the exact scopes it was
# granted for. token.json from earlier stages was authorized for gmail.readonly
# ONLY, so it does NOT cover the new spreadsheets scope. A token can't be
# "upgraded" to more scopes — the user must consent again. That's why
# get_credentials() below detects a scope mismatch, discards the stale token,
# and re-triggers the browser consent flow with the full scope set.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/spreadsheets",
]


# ---------------------------------------------------------------------------
# OAuth (see gmail_test.py for the full flow explanation):
#   reuse token.json -> refresh if expired -> else browser consent -> save.
# ---------------------------------------------------------------------------
def get_credentials():
    """Return valid Google API credentials, running the OAuth flow if needed."""
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    # Scope-change detection: if the saved token was granted a NARROWER set of
    # scopes than we now require (e.g. it predates adding the Sheets scope), it
    # cannot grant the new permission. Discard it so the full consent flow runs
    # again below. (A token can gain scopes only via fresh user consent.)
    if creds and not set(SCOPES).issubset(set(creds.scopes or [])):
        creds = None
        if os.path.exists("token.json"):
            os.remove("token.json")

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=0)
        with open("token.json", "w", encoding="utf-8") as token_file:
            token_file.write(creds.to_json())

    return creds


def get_service():
    """Build an authorized Gmail API client."""
    return build("gmail", "v1", credentials=get_credentials())


# ---------------------------------------------------------------------------
# HTML -> plain text.
# Real emails are usually HTML. We do NOT want to send raw markup to the model
# (it's noisy and wastes tokens), so we strip tags to readable text using
# Python's stdlib html.parser — no extra dependency. We also drop <script>/
# <style> contents, which are never human-readable.
# ---------------------------------------------------------------------------
class _HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._chunks = []
        self._skip = False  # True while inside <script>/<style>

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            self._chunks.append(data)

    def get_text(self):
        return "".join(self._chunks)


def strip_html(html_text):
    """Return human-readable text from an HTML string, never raising."""
    parser = _HTMLTextExtractor()
    try:
        parser.feed(html_text)
    except Exception:
        # If the HTML is so malformed the parser chokes, fall back to the raw
        # string rather than crashing the whole run.
        return html_text
    return parser.get_text()


def _collapse_whitespace(text):
    """Collapse runs of whitespace/newlines into single spaces for a tidy snippet."""
    return re.sub(r"\s+", " ", text).strip()


def _decode_part(data):
    """Decode a base64url-encoded Gmail body part to a string (lenient)."""
    # errors='replace' guards against weird encodings in real mail.
    return base64.urlsafe_b64decode(data.encode("utf-8")).decode(
        "utf-8", errors="replace"
    )


def _extract_body(payload):
    """
    Walk a Gmail message payload and return (text, is_html).

    Gmail messages are often multipart (text/plain + text/html, sometimes
    nested). We PREFER text/plain; if only HTML exists we return that and let
    the caller strip it. Recurses through nested 'parts'. Returns ("", False)
    if no readable body is found (e.g. attachment-only mail).
    """
    mime = payload.get("mimeType", "")
    data = payload.get("body", {}).get("data")

    if mime == "text/plain" and data:
        return _decode_part(data), False
    if mime == "text/html" and data:
        return _decode_part(data), True

    parts = payload.get("parts", [])
    # First pass: prefer a plain-text part anywhere in the tree.
    for part in parts:
        text, is_html = _extract_body(part)
        if text and not is_html:
            return text, False
    # Second pass: accept HTML if that's all there is.
    for part in parts:
        text, is_html = _extract_body(part)
        if text:
            return text, is_html

    return "", False


def _header(headers, name, default):
    """Pull a single header value (case-insensitive) from the header list."""
    return next(
        (h["value"] for h in headers if h["name"].lower() == name.lower()),
        default,
    )


def fetch_recent_emails(service, max_results=15, snippet_chars=500):
    """
    Fetch the most recent `max_results` emails as a list of dicts:
        {"sender": ..., "subject": ..., "body": <plain-text snippet>}

    The body is HTML-stripped, whitespace-collapsed, and truncated to
    `snippet_chars` characters — we only send a short snippet to the model
    (privacy + speed), never the full raw email. Per-message errors are caught
    so one bad email cannot crash the whole fetch.
    """
    results = (
        service.users()
        .messages()
        .list(userId="me", maxResults=max_results)
        .execute()
    )
    messages = results.get("messages", [])

    emails = []
    for item in messages:
        try:
            msg = (
                service.users()
                .messages()
                .get(userId="me", id=item["id"], format="full")
                .execute()
            )
            payload = msg.get("payload", {})
            headers = payload.get("headers", [])
            subject = _header(headers, "Subject", "(no subject)")
            sender = _header(headers, "From", "(unknown sender)")

            raw_body, is_html = _extract_body(payload)
            text_body = strip_html(raw_body) if is_html else raw_body
            snippet = _collapse_whitespace(text_body)[:snippet_chars]

            # internalDate is the message's received time in epoch milliseconds;
            # convert to a YYYY-MM-DD date for the tracker's Date column.
            internal = msg.get("internalDate")
            if internal:
                date_str = datetime.datetime.fromtimestamp(
                    int(internal) / 1000
                ).strftime("%Y-%m-%d")
            else:
                date_str = ""

            emails.append(
                {
                    "date": date_str,
                    "sender": sender,
                    "subject": subject,
                    "body": snippet,
                }
            )
        except Exception as exc:
            # Never let a single malformed message abort the run; record a
            # placeholder so the caller still sees something for it.
            print(f"  [WARN] Could not fetch/parse a message ({exc}). Skipping body.")
            emails.append(
                {
                    "date": "",
                    "sender": "(unknown sender)",
                    "subject": "(could not read message)",
                    "body": "",
                }
            )

    return emails
