"""
agent.py — Stage 3.5 Step 4a: full pipeline (VERIFY MODE).

End-to-end run that ties every previously-built piece together:
  * gmail_client.py   — read my real inbox (READ-ONLY)
  * classifier.py     — classify each email with local llama3.2:3b
  * sheets_client.py  — APPEND matching emails to the Job Applications tab

Nothing here is new logic except the wiring, the column mapping, and the
duplicate guard. It is APPEND-ONLY and touches only the Job Applications tab.

Run it with:  python agent.py   (then check the Google Sheet)
"""

from collections import Counter

from dotenv import load_dotenv
import os

from classifier import ALLOWED_TYPES, classify_email
from gmail_client import fetch_recent_emails, get_service
from sheets_client import HEADERS, append_rows, get_sheets_service, read_all_rows

# ---------------------------------------------------------------------------
# CONFIG FLAG — WRITE_LISTINGS
#
# VERIFY MODE (True): my inbox currently holds mostly job_listings and no real
# confirmations/rejections yet, so we TEMPORARILY allow job_listing rows to be
# written too — that way I can watch the whole pipeline work on real data.
#
# Later (False): switch to funnel-only — write just the types that mean *I* am
# in a real application funnel (applied / interview / rejection / assessment)
# and SKIP job_listing. Flip this one flag to change the behavior.
#
# "other" is ALWAYS skipped, in either mode.
# ---------------------------------------------------------------------------
WRITE_LISTINGS = False

NUM_EMAILS = 15

# The four "funnel" types — these mean I personally have an application in motion.
FUNNEL_TYPES = {
    "application_confirmation",
    "interview_invite",
    "rejection",
    "assessment",
}

# Map each writable type to the tracker's Status value.
STATUS_BY_TYPE = {
    "application_confirmation": "Applied",
    "interview_invite": "Interviewing",
    "rejection": "Rejected",
    "assessment": "Assessment",
    "job_listing": "Considering",
}


def writable_types():
    """The set of types we write this run, per the WRITE_LISTINGS flag."""
    types = set(FUNNEL_TYPES)
    if WRITE_LISTINGS:
        types.add("job_listing")
    return types  # note: "other" is never included


def build_row(email, result):
    """Map one classified email to a row in HEADERS order (blanks elsewhere)."""
    type_ = result["type"]
    company = result["company"] or ""
    role = result["role"] or ""
    status = STATUS_BY_TYPE.get(type_, "")
    interview_stage = "Phone Screen" if type_ == "interview_invite" else ""
    notes = (
        f"Auto-added by agent | type={type_} | "
        f"conf={result['confidence']} | subject={email['subject']}"
    )

    # Fill only the columns we have data for; build by iterating HEADERS so
    # every other column is "" and stays in the correct position.
    values = {
        "Date": email.get("date", ""),
        "Company": company,
        "Role": role,
        "Status": status,
        "Interview Stage": interview_stage,
        "Notes": notes,
    }
    return [values.get(header, "") for header in HEADERS]


def _dup_key(company, role, status):
    """Normalized duplicate key: same Company + Role + Status (case-insensitive)."""
    return (company.strip().lower(), role.strip().lower(), status.strip().lower())


def load_existing_keys(existing_rows):
    """
    Build the set of Company+Role+Status keys already present in the sheet, so
    re-running the agent does not append emails it already wrote. We look up the
    column positions by header NAME from the sheet's own row 1 (robust even if
    the column order ever differs from our HEADERS constant).
    """
    keys = set()
    if not existing_rows:
        return keys

    header_row = existing_rows[0]
    pos = {name: i for i, name in enumerate(header_row)}
    ci, ri, si = pos.get("Company"), pos.get("Role"), pos.get("Status")

    def cell(row, idx):
        return row[idx] if (idx is not None and idx < len(row)) else ""

    for row in existing_rows[1:]:  # skip header
        keys.add(_dup_key(cell(row, ci), cell(row, ri), cell(row, si)))
    return keys


def main():
    load_dotenv()
    sheet_id = os.getenv("SHEET_ID")
    if not sheet_id:
        print("ERROR: SHEET_ID is not set in .env. Add a SHEET_ID=... line.")
        return

    allowed_to_write = writable_types()
    mode = "VERIFY (listings + funnel)" if WRITE_LISTINGS else "funnel-only"
    print(f"Mode: {mode}. Writing types: {sorted(allowed_to_write)}\n")

    # --- Read inbox -----------------------------------------------------
    print("Authenticating (read-only Gmail) and fetching recent emails...")
    gmail = get_service()
    emails = fetch_recent_emails(gmail, max_results=NUM_EMAILS)
    print(f"Fetched {len(emails)} emails. Classifying...\n")

    # --- Read existing sheet rows for duplicate guard -------------------
    sheets = get_sheets_service()
    existing_rows = read_all_rows(sheets, sheet_id)
    existing_keys = load_existing_keys(existing_rows)

    counts = Counter({t: 0 for t in ALLOWED_TYPES})
    counts["unparsed"] = 0

    rows_to_write = []
    seen_this_run = set()  # also de-dup within this single run
    skipped_dupes = 0

    # --- Classify + decide ---------------------------------------------
    for email in emails:
        result = classify_email(email)
        if result is None:
            counts["unparsed"] += 1
            continue

        type_ = result["type"]
        counts[type_] += 1

        if type_ not in allowed_to_write:
            # "other" (always) and "job_listing" (in funnel-only mode) land here.
            continue

        row = build_row(email, result)
        status = STATUS_BY_TYPE.get(type_, "")
        key = _dup_key(result["company"] or "", result["role"] or "", status)

        # Duplicate = same Company+Role+Status already in the sheet OR already
        # queued earlier in this same run.
        if key in existing_keys or key in seen_this_run:
            skipped_dupes += 1
            continue

        seen_this_run.add(key)
        rows_to_write.append(row)

    # --- Append (one batched append; append-only, never overwrites) -----
    written = 0
    if rows_to_write:
        append_rows(sheets, sheet_id, rows_to_write)
        written = len(rows_to_write)

    # --- Summary --------------------------------------------------------
    listings = counts["job_listing"]
    funnel = sum(counts[t] for t in FUNNEL_TYPES)
    other = counts["other"]

    print("=" * 60)
    print(f"Fetched {len(emails)} | listings {listings}, other {other}, funnel {funnel}")
    if counts["unparsed"]:
        print(f"  ({counts['unparsed']} email(s) could not be classified)")
    print(f"Wrote {written} rows | skipped {skipped_dupes} duplicates")


if __name__ == "__main__":
    main()
