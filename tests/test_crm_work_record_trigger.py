import sys
import unittest

from scripts.crm_work_record_trigger import (
    TriggerConfig,
    build_crm_command,
    output_summary,
    values_match,
)


class CrmWorkRecordTriggerTest(unittest.TestCase):
    def test_values_match_ignores_case_and_outer_spaces(self):
        self.assertTrue(values_match(" work record keyin ", "WORK RECORD KEYIN"))
        self.assertFalse(values_match("none", "work record keyin"))

    def test_build_crm_command_uses_safe_defaults_and_optional_limits(self):
        config = TriggerConfig(
            sheet_tab="V",
            trigger_cell="T1",
            trigger_value="work record keyin",
            reset_value="none",
            poll_seconds=15,
            once=True,
            dry_run=True,
            company="TOP高峰藥品",
            date="2026/5/29",
            max_rows=1,
            keep_open=True,
        )

        command = build_crm_command(config)

        self.assertEqual(command[0], sys.executable)
        self.assertTrue(
            command[1].endswith("scripts\\crm_work_record_lookup.py")
            or command[1].endswith("scripts/crm_work_record_lookup.py")
        )
        self.assertIn("--company", command)
        self.assertIn("TOP高峰藥品", command)
        self.assertIn("--date", command)
        self.assertIn("2026/5/29", command)
        self.assertIn("--max-rows", command)
        self.assertIn("1", command)
        self.assertIn("--keep-open", command)

    def test_output_summary_extracts_loaded_and_saved_rows(self):
        summary = output_summary(
            "Loaded 2 sheet rows\n"
            "Save record: sheet row 7\n"
            "Save record: sheet row 9\n"
        )

        self.assertEqual(summary["loaded_rows"], 2)
        self.assertEqual(summary["saved_sheet_rows"], ["7", "9"])


if __name__ == "__main__":
    unittest.main()
