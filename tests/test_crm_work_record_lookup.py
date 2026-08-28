import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.window_layout import WindowRect
from scripts import crm_work_record_lookup as lookup


def make_config(**overrides):
    values = {
        "crm_url": "http://crm.local",
        "account": "108010",
        "password": "pw",
        "company": "TOP",
        "customer_name": "中崙",
        "result_selection": "first",
        "browser": "edge",
        "keep_open": False,
        "from_sheet_v": True,
        "sheet_date": "2026/7/28",
        "sheet_tab": "V",
        "skip_test_record": True,
        "max_rows": 0,
        "start_row": 0,
        "status_column": "V",
        "ledger_path": Path("ledger.jsonl"),
    }
    values.update(overrides)
    return lookup.RunConfig(**values)


def sheet_row(*, date="2026/7/28", source="診所", work_nature="39003 新資料提供", content="拜訪紀錄"):
    row = [""] * 20
    row[7] = date
    row[14] = source
    row[15] = work_nature
    row[19] = content
    return row


class CrmWorkRecordLookupTest(unittest.TestCase):
    def test_apply_twinplay_browser_zoom_targets_crm_driver_window(self):
        class FakeDriver:
            title = "CRM"

            def __init__(self):
                self.rects = []

            def set_window_rect(self, x, y, width, height):
                self.rects.append((x, y, width, height))

        driver = FakeDriver()

        with (
            mock.patch.object(
                lookup,
                "half_screen_rect",
                return_value=WindowRect(x=0, y=0, width=640, height=752),
            ),
            mock.patch.object(lookup, "send_crm_twinplay_browser_zoom_to_window", return_value=True) as zoom,
        ):
            lookup.apply_twinplay_browser_zoom(driver)

        zoom.assert_called_once_with("CRM")
        self.assertEqual(driver.rects, [(0, 0, 640, 752), (0, 0, 640, 752)])

    def test_duplicate_ledger_row_writes_column_v_skip_status(self):
        config = make_config()
        record = lookup.WorkRecord(
            sheet_row=24,
            source_lookup_key="同安",
            work_nature="39003 新資料提供",
            record_content="提供空盒",
        )
        spreadsheet_id = "sheet-123"
        key = lookup.ledger_key(spreadsheet_id, config, record)
        writes = []

        def fake_update(_spreadsheet_id, range_name, values, service=None):
            writes.append((range_name, values[0][0]))

        with mock.patch.object(lookup, "update_sheet_values", side_effect=fake_update):
            pending = lookup.prepare_sheet_records_for_crm(
                object(),
                spreadsheet_id,
                config,
                [record],
                {key: {"key": key}},
            )

        self.assertEqual(pending, [])
        self.assertEqual(writes[0][0], "'V'!V24")
        self.assertIn("sent (duplicate ledger skipped)", writes[0][1])
        self.assertIn("Local ledger already contains this row; CRM save was not repeated.", writes[0][1])

    def test_missing_work_nature_writes_blocked_status_without_pending_save(self):
        config = make_config()
        record = lookup.WorkRecord(
            sheet_row=24,
            source_lookup_key="同安",
            work_nature="",
            record_content="提供空盒",
        )
        writes = []

        def fake_update(_spreadsheet_id, range_name, values, service=None):
            writes.append((range_name, values[0][0]))

        with mock.patch.object(lookup, "update_sheet_values", side_effect=fake_update):
            pending = lookup.prepare_sheet_records_for_crm(
                object(),
                "sheet-123",
                config,
                [record],
                {},
            )

        self.assertEqual(pending, [])
        self.assertEqual(writes[0][0], "'V'!V24")
        self.assertIn("blocked", writes[0][1])
        self.assertIn("Missing column P work nature", writes[0][1])
        self.assertIn("CRM save was not attempted", writes[0][1])

    def test_mark_record_sent_appends_local_ledger_and_writes_sent_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(ledger_path=Path(tmp) / "crm_work_record_ledger.jsonl")
            record = lookup.WorkRecord(
                sheet_row=22,
                source_lookup_key="高峰",
                work_nature="39003 新資料提供",
                record_content="CRM帳號詢問",
            )
            ledger = {}
            writes = []

            def fake_update(_spreadsheet_id, range_name, values, service=None):
                writes.append((range_name, values[0][0]))

            with mock.patch.object(lookup, "update_sheet_values", side_effect=fake_update):
                lookup.mark_record_sent(object(), "sheet-123", config, ledger, record)

            entries = lookup.load_local_ledger(config.ledger_path)
            key = lookup.ledger_key("sheet-123", config, record)
            self.assertIn(key, entries)
            self.assertIn(key, ledger)
            self.assertEqual(writes[0][0], "'V'!V22")
            self.assertIn("sent - CRM save completed.", writes[0][1])

    def test_load_sheet_v_records_can_start_from_row_24(self):
        config = make_config(start_row=24)
        values = [[""] * 20 for _ in range(25)]
        values[21] = sheet_row(source="row22")
        values[22] = sheet_row(source="row23")
        values[23] = sheet_row(source="row24")
        values[24] = sheet_row(source="row25")

        with mock.patch.object(lookup, "get_sheet_values", return_value=values):
            records = lookup.load_sheet_v_records(config, service=object(), spreadsheet_id="sheet-123")

        self.assertEqual([record.sheet_row for record in records], [24, 25])
        self.assertEqual([record.source_lookup_key for record in records], ["row24", "row25"])


if __name__ == "__main__":
    unittest.main()
