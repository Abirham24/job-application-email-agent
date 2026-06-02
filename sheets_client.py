"""
sheets_client.py — Shared Google Sheets helpers for the Job Applications tab.

Single source of truth for: the tab name, the column headers (in order), and
the read/append operations. Reused by sheets_write_test.py (Step 3) and
agent.py (Step 4a) so the header list and the append logic never drift.

APPEND vs UPDATE:
  * values.update writes to a SPECIFIC range and OVERWRITES whatever is there.
  * values.append finds the existing table and adds new rows AFTER the last
    data row, overwriting nothing.
Everything here is read-or-append ONLY — we never update/clear existing cells.
"""

from googleapiclient.discovery import build

from gmail_client import get_credentials

# The ONE tab we ever touch.
TAB_NAME = "Job Applications"

# The tab's real headers, in their actual column order. Rows are built in this
# exact order so each value lands in the correct column.
HEADERS = [
    "Date",
    "Company",
    "Role",
    "Job Level",
    "Link",
    "Status",
    "Interview Stage",
    "Applications Today",
    "Response Days",
    "Tailored Resume?",
    "Referral?",
    "Location",
    "Salary Range",
    "Notes",
]


def get_sheets_service():
    """Build an authorized Sheets API client (reuses the shared OAuth creds)."""
    return build("sheets", "v4", credentials=get_credentials())


def read_all_rows(service, sheet_id):
    """
    Return every populated row of the tab as a list of lists (row 0 = headers).
    Read-only. The tab name is quoted to handle the space in "Job Applications".
    """
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=sheet_id, range=f"'{TAB_NAME}'")
        .execute()
    )
    return result.get("values", [])


def append_rows(service, sheet_id, rows):
    """
    APPEND rows to the bottom of the tab. Never overwrites existing rows.
    `rows` is a list of row-lists. Returns the API result (includes the range
    that was written). USER_ENTERED so dates/strings are parsed like typed
    input; INSERT_ROWS forces brand-new rows.
    """
    return (
        service.spreadsheets()
        .values()
        .append(
            spreadsheetId=sheet_id,
            range=f"'{TAB_NAME}'",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": rows},
        )
        .execute()
    )
