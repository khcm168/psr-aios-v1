from datetime import date
from pathlib import Path
import unittest

from app.n1_report_pack import default_report_date
from app.n1_report_ppt import (
    _date_from_json_path,
    default_json_path,
    default_ppt_path,
)


class N1ReportDateTest(unittest.TestCase):
    def test_default_report_date_uses_next_monday(self):
        self.assertEqual(default_report_date(date(2026, 5, 22)), "2026-05-25")
        self.assertEqual(default_report_date(date(2026, 5, 25)), "2026-05-25")
        self.assertEqual(default_report_date(date(2026, 5, 26)), "2026-06-01")

    def test_ppt_defaults_follow_report_date(self):
        self.assertEqual(
            default_json_path("2026-05-25"),
            Path("data/report_packs/n1_report_pack_2026-05-25.json"),
        )
        self.assertEqual(
            default_ppt_path("2026-05-25"),
            Path("data/report_packs/N1_report_2026-05-25.pptx"),
        )

    def test_output_date_can_be_derived_from_json_path(self):
        self.assertEqual(
            _date_from_json_path(Path("data/report_packs/n1_report_pack_2026-05-25.json")),
            "2026-05-25",
        )


if __name__ == "__main__":
    unittest.main()
