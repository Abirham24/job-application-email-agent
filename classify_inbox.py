"""
classify_inbox.py — Stage 3: classify my REAL recent inbox.

Connects the two previously-tested pieces:
  * gmail_client.py  — read-only Gmail auth + fetch (Stage 1 logic)
  * classifier.py    — local llama3.2:3b classification (Stage 2 logic)

It fetches my 15 most recent emails, sends a short snippet of each to the
classifier, and prints a scannable summary plus a per-type count. This is an
INSPECTION stage: it prints only and writes to NO tracker. OAuth scope stays
read-only.

Run it with:  python classify_inbox.py
"""

from collections import Counter

from classifier import ALLOWED_TYPES, classify_email
from gmail_client import fetch_recent_emails, get_service

# How many recent emails to inspect this run.
NUM_EMAILS = 15


def main():
    print("Authenticating to Gmail (read-only) and fetching recent emails...")
    service = get_service()
    emails = fetch_recent_emails(service, max_results=NUM_EMAILS)
    print(f"Fetched {len(emails)} emails. Classifying with the local model...\n")

    # Tally how many of each type we see. Pre-seed with every allowed type so
    # the final summary lists all categories (including zeros), plus a bucket
    # for emails the model couldn't classify.
    counts = Counter({t: 0 for t in ALLOWED_TYPES})
    counts["unparsed"] = 0

    for email in emails:
        print("=" * 72)
        print(f"Subject: {email['subject']}")
        print(f"From:    {email['sender']}")

        result = classify_email(email)
        if result is None:
            # classify_email already printed a [WARN] with the raw output.
            counts["unparsed"] += 1
            print("  -> Skipped (could not parse a valid classification).")
            continue

        counts[result["type"]] += 1
        print(f"  type:       {result['type']}")
        print(f"  company:    {result['company']}")
        print(f"  role:       {result['role']}")
        print(f"  confidence: {result['confidence']}")

    # ----- Step 5: summary tally ---------------------------------------
    print("=" * 72)
    print("\nSummary — counts by type:")
    for type_name in sorted(ALLOWED_TYPES):
        print(f"  {type_name:26} {counts[type_name]}")
    if counts["unparsed"]:
        print(f"  {'unparsed (malformed)':26} {counts['unparsed']}")
    print(f"\nTotal emails processed: {len(emails)}")


if __name__ == "__main__":
    main()
