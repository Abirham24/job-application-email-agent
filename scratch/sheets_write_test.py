"""
sheets_write_test.py — Stage 3.5 Step 3: append ONE hardcoded test row.

Proves the script can WRITE to the `Job Applications` tab by appending a single,
obviously-fake test row. No Gmail, no classifier, no loop — writing is verified
in isolation before wiring real data.

APPEND vs UPDATE:
  * values.update writes to a SPECIFIC range (e.g. A6:N6) and OVERWRITES whatever
    is already in those cells. Get the range wrong and you clobber real data.
  * values.append finds the existing table under the given range and adds new
    rows AFTER the last row of data, overwriting nothing.
We use append precisely because it cannot overwrite existing rows — the safe
choice for adding a record to the bottom of the tracker.

Run it with:  python sheets_write_test.py
Then open the Google Sheet and confirm the test row appears at the bottom.
"""

import datetime
import os

from dotenv import load_dotenv

# Tab name, headers, and the append logic now live in sheets_client.py (shared
# with agent.py) so they cannot drift.
from sheets_client import HEADERS, TAB_NAME, append_rows, get_sheets_service


def build_test_row():
    """Return one hardcoded, clearly-fake test row aligned to HEADERS."""
    today = datetime.date.today().isoformat()  # YYYY-MM-DD

    # Map only the fields we want to fill; everything else stays blank. Building
    # the list by iterating HEADERS guarantees correct column alignment and that
    # unspecified columns become "" (not skipped/misaligned).
    values = {
        "Date": today,
        "Company": "TEST COMPANY (delete me)",
        "Role": "Test Role",
        "Status": "Applied",
        "Notes": "Written by agent — Stage 3.5 Step 3 test row",
    }
    return [values.get(header, "") for header in HEADERS]


def main():
    load_dotenv()
    sheet_id = os.getenv("SHEET_ID")
    if not sheet_id:
        print("ERROR: SHEET_ID is not set in .env. Add a SHEET_ID=... line.")
        return

    # Reuse existing creds/token — scopes already include spreadsheets, so no
    # re-consent is needed this step.
    service = get_sheets_service()

    row = build_test_row()

    # APPEND the row (never overwrites existing data). See sheets_client for the
    # append-vs-update explanation.
    result = append_rows(service, sheet_id, [row])

    # The API tells us exactly where it wrote.
    updated_range = result.get("updates", {}).get("updatedRange", "(unknown)")
    updated_rows = result.get("updates", {}).get("updatedRows", 0)
    print(f"Appended {updated_rows} row to {updated_range}")
    print("Open the Google Sheet to confirm the test row landed in the right columns.")


if __name__ == "__main__":
    main()
