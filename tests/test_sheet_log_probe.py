from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from app.sheet_log_probe import build_probe_row


class SheetLogProbeTest(unittest.TestCase):
    def test_build_probe_row_contains_diagnostic_fields(self):
        timestamp = datetime(2026, 4, 25, 1, 2, 3, tzinfo=timezone.utc)

        with patch("app.operation_log.platform.node", return_value="test-host"):
            with patch("app.operation_log.getpass.getuser", return_value="tester"):
                row = build_probe_row(
                    project_name="psr-aios-v1",
                    message="hello sheet log",
                    timestamp=timestamp,
                )

        self.assertEqual(
            row,
            [
                "2026-04-25T01:02:03+00:00",
                "psr-aios-v1",
                "sheet-log-probe",
                "ok",
                "Verify real Google Sheets append/readback access.",
                '{"message": "hello sheet log"}',
                "hello sheet log",
                "test-host",
                "tester",
            ],
        )


if __name__ == "__main__":
    unittest.main()
