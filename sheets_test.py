"""
sheets_test.py — Stage 3.5 Step 2: read-only Google Sheets connection test.

Proves the script can authenticate to Google and READ from the live tracker
spreadsheet. This is a CONNECTION TEST ONLY — it does not write, append, or
modify a single cell. We verify reading in isolation before adding any write
logic in the next step.

It reuses the existing OAuth setup in gmail_client.py (credentials.json /
token.json). Because gmail_client.SCOPES now includes the Sheets scope in
ADDITION to gmail.readonly, the old token (gmail-only) no longer covers what we
need — so the first run will pop a browser consent screen again to re-authorize
with the new scopes. See gmail_client.get_credentials() for that logic.

Run it with:  python sheets_test.py
"""

import os

from dotenv import load_dotenv
from googleapiclient.discovery import build

from gmail_client import get_credentials

# The tab we read from in the tracker spreadsheet.
TAB_NAME = "Job Applications"


def main():
    # Step 1: load SHEET_ID from .env (never hardcoded — keeps the ID out of
    # source control alongside other secrets).
    load_dotenv()
    sheet_id = os.getenv("SHEET_ID")
    if not sheet_id:
        print("ERROR: SHEET_ID is not set in .env. Add a SHEET_ID=... line.")
        return

    # Step 2: authenticate (re-consents if scopes changed) and build a Sheets
    # API client.
    creds = get_credentials()
    service = build("sheets", "v4", credentials=creds)

    # Step 3: read the tab's values. Quoting the tab name handles the space in
    # "Job Applications". Passing just the tab title returns every populated
    # row/column in that sheet.
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=sheet_id, range=f"'{TAB_NAME}'")
        .execute()
    )
    values = result.get("values", [])

    if not values:
        print(f"Connected to sheet, but tab '{TAB_NAME}' appears to be empty.")
        return

    # Row 1 is the header; everything after it is a data row.
    headers = values[0]
    data_row_count = len(values) - 1

    # Step 4: report what we found.
    print(f"Connected to sheet. Tab: {TAB_NAME}")
    print(f"Headers: {', '.join(headers)}")
    print(f"Existing data rows: {data_row_count}")


if __name__ == "__main__":
    main()
