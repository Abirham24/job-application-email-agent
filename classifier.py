"""
classifier.py — Shared email-classification logic (local Ollama model).

This module is the SINGLE SOURCE OF TRUTH for how we classify an email. It was
extracted from the Stage 2 test script so that both the Stage 2 sample test
(`classify_test.py`) and the Stage 3 real-inbox run (`classify_inbox.py`) call
the exact same prompt and parsing — no duplication, no drift.

It does the model call, demands strict JSON, and parses it safely (never
crashes on bad model output).
"""

import json

import ollama

# Small, local model — keeps email content on-device and is fast enough for
# short-text classification.
MODEL = "llama3.2:3b"

# The ONLY accepted type labels. Anything outside this set is treated as
# malformed. Shared by the prompt and the validator so they cannot drift apart.
ALLOWED_TYPES = {
    "job_listing",
    "application_confirmation",
    "interview_invite",
    "rejection",
    "assessment",
    "other",
}

# ---------------------------------------------------------------------------
# Prompt design (see Stage 2 notes):
#   * Every category gets a crisp one-line definition.
#   * The job_listing vs application_confirmation confusion is called out
#     explicitly because that is where small models slip most.
#   * company/role must be extracted (null when absent) so downstream keys
#     always exist.
#   * confidence float lets us threshold later.
#   * RAW JSON ONLY — forbidden to wrap in markdown fences (and we also strip
#     fences defensively in code).
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are an email classifier for a job-application tracking tool.
Classify a single email into exactly ONE of these categories:

- "job_listing": The email advertises that a job opening EXISTS or invites me to
  apply. I have NOT applied yet. (e.g. "Company X has a Data Scientist opening",
  LinkedIn/ZipRecruiter "new jobs for you" alerts.)
- "application_confirmation": The email confirms that I PERSONALLY submitted an
  application. (e.g. "Thank you for applying", "We received your application".)
- "interview_invite": The email invites me to an interview, screening call, or
  asks to schedule a conversation.
- "assessment": The email asks me to complete an online assessment, coding test,
  take-home, or similar evaluation step.
- "rejection": The email tells me I was not selected / they are moving forward
  with other candidates.
- "other": Anything that does not fit the above (newsletters, security alerts,
  promotions, welcome emails, unrelated mail).

CRITICAL DISTINCTION: "job_listing" means a job EXISTS and I have not applied.
"application_confirmation" means I ALREADY APPLIED. Do not confuse these two.

Also extract:
- "company": the HIRING EMPLOYER's name if present, otherwise null.
  IMPORTANT: "company" must be the employer that is actually hiring, NOT the job
  board or the email sender. ZipRecruiter, LinkedIn, and Indeed are senders/job
  boards, NOT employers. If the actual hiring employer is not stated in the
  email, set "company" to null.
- "role": the job title/role if present, otherwise null.
- "confidence": your confidence as a number from 0.0 to 1.0.

Return ONLY a valid JSON object, with no extra text, no explanation, and no
markdown code fences. The JSON must have exactly these keys:
{"type": "...", "company": "... or null", "role": "... or null", "confidence": 0.0}
"""


def build_user_message(email):
    """Format one email (dict with sender/subject/body) for the model."""
    return (
        f"From: {email['sender']}\n"
        f"Subject: {email['subject']}\n"
        f"Body: {email['body']}"
    )


def strip_code_fences(text):
    """
    Defensively remove markdown code fences the model may add despite being
    told not to. Handles ```json ... ``` and bare ``` ... ``` wrappers.
    We only strip fences; we do NOT try to "repair" broken JSON — if it is
    still invalid after this, we report it as malformed rather than guess.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
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
    output — the caller can keep going through the remaining emails.
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

    # ----- Safe parsing -------------------------------------------------
    # 1) Strip any accidental markdown fences.
    # 2) json.loads; a JSONDecodeError means malformed output -> warn, no crash.
    # 3) Validate "type" against ALLOWED_TYPES; if not, treat as malformed.
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

    # Normalize keys so callers can rely on all four always being present.
    return {
        "type": result.get("type"),
        "company": result.get("company"),
        "role": result.get("role"),
        "confidence": result.get("confidence"),
    }
