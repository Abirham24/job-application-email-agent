"""
classify_test.py — Stage 2: Email classification with a local Ollama model.

Standalone test of the MODEL + PROMPT in isolation (no Gmail, no tracker). It
feeds hardcoded sample emails to the classifier and prints the structured
result.

The classification logic itself now lives in classifier.py (shared with the
Stage 3 real-inbox run) so there is a single source of truth for the prompt and
parsing. This script only owns the sample data and the printing.

Run it with:  python classify_test.py
(Prerequisite: Ollama running and the model pulled: ollama pull llama3.2:3b)
"""

from classifier import MODEL, classify_email

# ---------------------------------------------------------------------------
# Hardcoded sample emails: a deliberate spread of categories, including the
# easy-to-confuse pair (job_listing vs application_confirmation) and one piece
# of "noise" so we can confirm the model routes irrelevant mail to "other".
# ---------------------------------------------------------------------------
SAMPLE_EMAILS = [
    {
        "sender": "jobs@deltek.com",
        "subject": "Deltek, Inc. has a Data Scientist opening now",
        "body": (
            "A new Data Scientist position is now open at Deltek, Inc. "
            "Apply today to join our analytics team. Click here to view the "
            "full job description and submit your application."
        ),
    },
    {
        "sender": "no-reply@greenhouse.io",
        "subject": "Thank you for applying to Acme Corp",
        "body": (
            "Hi, thank you for applying to the Software Engineer role at "
            "Acme Corp. We have received your application and our team will "
            "review it shortly."
        ),
    },
    {
        "sender": "recruiting@hooli.com",
        "subject": "Interview invitation — Backend Engineer",
        "body": (
            "We were impressed with your background and we'd like to schedule "
            "a call to discuss the Backend Engineer role. Are you available "
            "next week for a 45-minute technical interview?"
        ),
    },
    {
        "sender": "talent@initech.com",
        "subject": "Update on your application",
        "body": (
            "Thank you for your interest in Initech. After careful "
            "consideration, we have decided to move forward with other "
            "candidates for this position. We wish you the best."
        ),
    },
    {
        "sender": "assessments@codescreen.com",
        "subject": "Action required: complete your coding assessment",
        "body": (
            "As the next step in the process for the Full Stack Developer "
            "role at Globex, please complete this online coding assessment "
            "within 72 hours. The test takes about 90 minutes."
        ),
    },
    {
        "sender": "newsletter@techweekly.com",
        "subject": "This week in tech: 10 stories you missed",
        "body": (
            "Your weekly digest of the biggest technology headlines, product "
            "launches, and industry gossip. Unsubscribe at any time."
        ),
    },
]


def main():
    print(f"Classifying {len(SAMPLE_EMAILS)} sample emails with '{MODEL}'...\n")

    for email in SAMPLE_EMAILS:
        print("=" * 70)
        print(f"Subject: {email['subject']}")
        result = classify_email(email)
        if result is None:
            print("  -> Skipped (could not parse a valid classification).")
            continue

        print(f"  type:       {result['type']}")
        print(f"  company:    {result['company']}")
        print(f"  role:       {result['role']}")
        print(f"  confidence: {result['confidence']}")

    print("=" * 70)


if __name__ == "__main__":
    main()
