from __future__ import annotations

from typing import Any, Sequence

try:
    import gspread
except (ImportError, ModuleNotFoundError):
    gspread = None

try:
    from google.oauth2.service_account import Credentials
except (ImportError, ModuleNotFoundError):
    Credentials = None

from app.config import Settings
from app.operation_log import LOG_HEADER


SHEETS_SCOPES = ("https://www.googleapis.com/auth/spreadsheets",)


class GoogleSheetsClient:
    def __init__(
        self,
        spreadsheet_id: str,
        worksheet_name: str,
        gspread_client: Any,
    ) -> None:
        self.spreadsheet_id = spreadsheet_id
        self.worksheet_name = worksheet_name
        self.gspread_client = gspread_client

    @classmethod
    def from_settings(cls, settings: Settings) -> "GoogleSheetsClient":
        if gspread is None or Credentials is None:
            raise RuntimeError(
                "Google Sheets dependencies are missing. Run `pip install -r requirements.txt`."
            )

        credentials = Credentials.from_service_account_file(
            settings.google_credentials_path,
            scopes=list(SHEETS_SCOPES),
        )
        return cls(
            spreadsheet_id=settings.spreadsheet_id,
            worksheet_name=settings.worksheet_name,
            gspread_client=gspread.authorize(credentials),
        )

    def append_row(self, values: Sequence[str]) -> None:
        worksheet = self._worksheet()
        worksheet.append_row(list(values), value_input_option="USER_ENTERED")

    def ensure_header(self, headers: Sequence[str]) -> None:
        worksheet = self._worksheet()
        existing = worksheet.row_values(1)
        if existing[: len(headers)] == list(headers):
            return
        worksheet.update("A1", [list(headers)], value_input_option="USER_ENTERED")

    def spreadsheet(self) -> Any:
        return self.gspread_client.open_by_key(self.spreadsheet_id)

    def worksheet_values(self, worksheet_name: str) -> list[list[str]]:
        return self.spreadsheet().worksheet(worksheet_name).get_all_values()

    def _worksheet(self) -> Any:
        spreadsheet = self.spreadsheet()
        try:
            return spreadsheet.worksheet(self.worksheet_name)
        except _worksheet_not_found_error():
            worksheet = spreadsheet.add_worksheet(
                title=self.worksheet_name,
                rows=1000,
                cols=10,
            )
            worksheet.append_row(
                LOG_HEADER,
                value_input_option="USER_ENTERED",
            )
            return worksheet


def _worksheet_not_found_error() -> type[Exception]:
    if gspread is None:
        return LookupError
    return gspread.WorksheetNotFound
