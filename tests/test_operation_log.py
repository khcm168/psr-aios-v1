from datetime import datetime, timezone
from pathlib import Path
import unittest
from unittest.mock import patch

from app.operation_log import (
    build_file_sync_context,
    build_operation_row,
    build_result_link_details,
    operation_log_row_matches,
    read_last_operation_log_row,
)


class OperationLogTest(unittest.TestCase):
    def test_build_operation_row_records_tracking_fields(self):
        timestamp = datetime(2026, 4, 25, 2, 3, 4, tzinfo=timezone.utc)

        with patch("app.operation_log.platform.node", return_value="test-host"):
            with patch("app.operation_log.getpass.getuser", return_value="tester"):
                row = build_operation_row(
                    project_name="psr-aios-v1",
                    operation="sample_job",
                    result="success",
                    purpose="prove logging shape",
                    variables={"count": 3, "tab": "log"},
                    details="completed",
                    timestamp=timestamp,
                )

        self.assertEqual(
            row,
            [
                "2026-04-25T02:03:04+00:00",
                "psr-aios-v1",
                "sample_job",
                "success",
                "prove logging shape",
                '{"count": 3, "tab": "log"}',
                "completed",
                "test-host",
                "tester",
            ],
        )

    def test_operation_log_row_matches_ignores_extra_blank_sheet_cells(self):
        expected = ["time", "project", "operation"]
        actual = ["time", "project", "operation", "", ""]

        self.assertTrue(operation_log_row_matches(expected, actual))

    def test_operation_log_row_matches_rejects_different_last_row(self):
        expected = ["time", "project", "operation"]
        actual = ["time", "project", "other"]

        self.assertFalse(operation_log_row_matches(expected, actual))

    def test_read_last_operation_log_row_returns_final_sheet_row(self):
        class FakeClient:
            def worksheet_values(self, worksheet_name):
                self.worksheet_name = worksheet_name
                return [["header"], ["latest"]]

        class FakeSettings:
            worksheet_name = "log"

        client = FakeClient()
        row = read_last_operation_log_row(settings=FakeSettings(), client=client)

        self.assertEqual(row, ["latest"])
        self.assertEqual(client.worksheet_name, "log")

    def test_build_result_link_details_returns_sheets_hyperlink_formula(self):
        details = build_result_link_details(
            message='Report "ready".',
            result_path=Path("data") / "report.md",
            sync_context={"provider": "OneDrive"},
        )

        self.assertTrue(details.startswith('=HYPERLINK("file:///'))
        self.assertIn('Report ""ready"". Open result (OneDrive local sync)', details)

    def test_build_file_sync_context_detects_onedrive_paths(self):
        context = build_file_sync_context(
            [Path("C:/Users/test/OneDrive/Desktop/report.md")]
        )

        self.assertEqual(context["provider"], "OneDrive")
        self.assertEqual(context["local_sync_root"], "C:\\Users\\test\\OneDrive")
        self.assertIn("OneDrive-synced", context["note"])


if __name__ == "__main__":
    unittest.main()
