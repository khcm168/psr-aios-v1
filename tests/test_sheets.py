import unittest

from app.sheets import GoogleSheetsClient


class FakeSpreadsheet:
    def __init__(self):
        self.created = None
        self.existing = FakeWorksheet()

    def worksheet(self, name):
        return self.existing

    def add_worksheet(self, title, rows, cols):
        self.created = FakeWorksheet()
        return self.created


class FakeWorksheet:
    def __init__(self):
        self.rows = []
        self.first_row = []

    def append_row(self, row, value_input_option):
        self.rows.append((row, value_input_option))

    def row_values(self, row_number):
        return self.first_row if row_number == 1 else []

    def update(self, range_name, values, value_input_option):
        self.rows.append((range_name, values, value_input_option))
        if range_name == "A1":
            self.first_row = values[0]


class FakeClient:
    def __init__(self):
        self.spreadsheet = FakeSpreadsheet()

    def open_by_key(self, spreadsheet_id):
        self.spreadsheet_id = spreadsheet_id
        return self.spreadsheet


class GoogleSheetsClientTest(unittest.TestCase):
    def test_append_row_writes_to_configured_spreadsheet_and_worksheet(self):
        fake_client = FakeClient()
        client = GoogleSheetsClient(
            spreadsheet_id="sheet-123",
            worksheet_name="log",
            gspread_client=fake_client,
        )

        client.append_row(["timestamp", "source", "message"])

        self.assertEqual(fake_client.spreadsheet_id, "sheet-123")
        self.assertEqual(
            fake_client.spreadsheet.existing.rows,
            [(["timestamp", "source", "message"], "USER_ENTERED")],
        )

    def test_ensure_header_updates_first_row_when_needed(self):
        fake_client = FakeClient()
        client = GoogleSheetsClient(
            spreadsheet_id="sheet-123",
            worksheet_name="log",
            gspread_client=fake_client,
        )

        client.ensure_header(["occurred_at", "project"])

        self.assertEqual(
            fake_client.spreadsheet.existing.rows,
            [("A1", [["occurred_at", "project"]], "USER_ENTERED")],
        )
