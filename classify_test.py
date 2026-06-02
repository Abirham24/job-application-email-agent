"""
classify_test.py — Stage 2: Email classification with a local Ollama model.

This is a STANDALONE test. It does NOT touch Gmail and does NOT touch any
tracker. It feeds a handful of hardcoded sample emails to the local
`llama3.2:3b` model via Ollama, asks for a structured JSON classification,
parses the result safely, and prints it.

The point of this stage is to validate the MODEL + PROMPT in isolation before
wiring classification into the real pipeline. Run it with:

    python classify_test.py

(Prerequisite: Ollama is installed and running, and the model is pulled:
    ollama pull llama3.2:3b )
"""

import json

import ollama

# ---------------------------------------------------------------------------
# The model we talk to. Small, local, fast — good enough for short-text
# classification and keeps everything on-device (no email content leaves the
# machine).
# ---------------------------------------------------------------------------
MODEL = "llama3.2:3b"

# The ONLY type labels we accept back from the model. Anything outside this set
# is treated as malformed (see safe-parsing logic below). Keeping this as the
# single source of truth means the prompt and the validator can't drift apart.
ALLOWED_TYPES = {
    "job_listing",
    "application_confirmation",
    "interview_invite",
    "rejection",
    "assessment",
    "other",
}

# ---------------------------------------------------------------------------
# Step 1 — Hardcoded sample emails.
# A deliberate spread of categories, including the easy-to-confuse pair
# (job_listing vs application_confirmation) and one piece of "noise" so we can
# confirm the model routes irrelevant mail to "other".
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

# ---------------------------------------------------------------------------
# Step 3 — Prompt design.
#
# Design choices baked into this prompt:
#   * We enumerate every category with a one-line definition so the model has
#     crisp boundaries instead of guessing from the label name.
#   * We call out the single most common confusion explicitly: a job_listing
#     announces that a job EXISTS (I have not applied), whereas an
#     application_confirmation acknowledges that I PERSONALLY applied. This one
#     distinction is where small models slip most, so it gets its own emphasis.
#   * We demand company/role extraction with explicit `null` when absent, so
#     downstream code can rely on the keys always being present.
#   * We demand a confidence float so we can later threshold low-confidence
#     classifications.
#   * We demand RAW JSON ONLY (no prose, no markdown fences). Small models love
#     to wrap output in ```json fences or add a chatty sentence; we forbid it in
#     the prompt AND strip it defensively in code (belt and suspenders).
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are an email classifier for a job-application tracking tool.
Classify a single email into exactly ONE of these categories:

- "job_listing": The email advertises that a job opening EXISTS or invites me to
  apply. I have NOT applied yet. (e.g. "Company X has a Data Scientist opening".)
- "application_confirmation": The email confirms that I PERSONALLY submitted an
  application. (e.g. "Thank you for applying", "We received your application".)
- "interview_invite": The email invites me to an interview, screening call, or
  asks to schedule a conversation.
- "assessment": The email asks me to complete an online assessment, coding test,
  take-home, or similar evaluation step.
- "rejection": The email tells me I was not selected / they are moving forward
  with other candidates.
- "other": Anything that does not fit the above (newsletters, security alerts,
  promotions, unrelated mail).

CRITICAL DISTINCTION: "job_listing" means a job EXISTS and I have not applied.
"application_confirmation" means I ALREADY APPLIED. Do not confuse these two.

Also extract:
- "company": the hiring company's name if present, otherwise null.
- "role": the job title/role if present, otherwise null.
- "confidence": your confidence as a number from 0.0 to 1.0.

Return ONLY a valid JSON object, with no extra text, no explanation, and no
markdown code fences. The JSON must have exactly these keys:
{"type": "...", "company": "... or null", "role": "... or null", "confidence": 0.0}
"""


def build_user_message(email):
    """Format one email into the content the model will classify."""
    return (
        f"From: {email['sender']}\n"
        f"Subject: {email['subject']}\n"
        f"Body: {email['body']}"
    )


def strip_code_fences(text):
    """
    Defensively remove markdown code fences the model may add despite being
    told not to. Handles ```json ... ``` and bare ``` ... ``` wrappers.
    We only strip fences; we do NOT try to "repair" broken JSON — if it's still
    invalid after this, we report it as malformed rather than guess.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Drop the first line (``` or ```json) and a trailing ``` if present.
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned


def classify_email(email):
    """
    Send one email to the model and return a parsed result dict, or None if the
    output could not be safely parsed/validated. Never raises on bad model
    output — the caller can keep going through the remaining samples.
    """
    response = ollama.chat(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_message(email)},
        ],
        # Low temperature: classification should be deterministic, not creative.
        options={"temperature": 0},
    )
    raw = response["message"]["content"]

    # ----- Step 5: safe parsing -----------------------------------------
    # 1) Strip any accidental markdown fences.
    # 2) Try json.loads; a JSONDecodeError means malformed output -> warn,
    #    don't crash.
    # 3) Validate the "type" is in our allowed set; if not, treat as malformed.
    cleaned = strip_code_fences(raw)
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        print("  [WARN] Model did not return valid JSON. Raw output was:")
        print(f"  {raw!r}")
        return None

    if not isinstance(result, dict) or result.get("type") not in ALLOWED_TYPES:
        print("  [WARN] Missing or invalid 'type' in model output. Raw output was:")
        print(f"  {raw!r}")
        return None

    # Normalize the keys we care about so printing is uniform even if the model
    # omitted optional fields.
    return {
        "type": result.get("type"),
        "company": result.get("company"),
        "role": result.get("role"),
        "confidence": result.get("confidence"),
    }


def main():
    print(f"Classifying {len(SAMPLE_EMAILS)} sample emails with '{MODEL}'...\n")

    for email in SAMPLE_EMAILS:
        # Step 6: show the original subject, then the structured result.
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
