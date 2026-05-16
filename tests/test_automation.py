from datetime import datetime, timezone
import unittest

from app.automation import build_status_row


class BuildStatusRowTest(unittest.TestCase):
    def test_build_status_row_uses_utc_iso_timestamp(self):
        row = build_status_row(
            message="hello",
            source="unit-test",
            timestamp=datetime(2026, 4, 22, 14, 30, tzinfo=timezone.utc),
        )

        self.assertEqual(row, ["2026-04-22T14:30:00+00:00", "unit-test", "hello"])
