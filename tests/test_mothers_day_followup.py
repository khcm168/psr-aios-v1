import unittest
from pathlib import Path

from app.mothers_day_followup import (
    MothersDayFollowupConfig,
    build_followup_pack,
    build_line_text,
    classify_status,
    render_markdown,
    table_from_values,
)


class FakeSpreadsheet:
    title = "地區會議資料V7.0 beta"

    def __init__(self, worksheets):
        self.worksheets = worksheets

    def worksheet(self, name):
        if name not in self.worksheets:
            raise LookupError(name)
        return FakeWorksheet(self.worksheets[name])


class FakeWorksheet:
    def __init__(self, values):
        self.values = values

    def get_all_values(self):
        return self.values


class MothersDayFollowupTest(unittest.TestCase):
    def test_table_from_values_detects_header_and_source_rows(self):
        table = table_from_values(
            [
                ["", ""],
                ["區域", "客戶名稱", "追蹤狀態", "備註"],
                ["N1", "甲診所", "追蹤中", "活動後待確認"],
            ]
        )

        self.assertEqual(table["header_row"], 2)
        self.assertEqual(table["headers"], ["區域", "客戶名稱", "追蹤狀態", "備註"])
        self.assertEqual(table["records"][0]["source_row"], 3)

    def test_table_from_values_preserves_unnamed_extra_columns(self):
        table = table_from_values(
            [
                ["贈品", "業務區碼", "郵遞區號", "診所名稱"],
                ["Q10", "N1", "104", "甲診所", "追蹤中"],
            ]
        )

        self.assertEqual(table["headers"], ["贈品", "業務區碼", "郵遞區號", "診所名稱", "column_5"])
        self.assertEqual(table["records"][0]["values"]["column_5"], "追蹤中")

    def test_build_followup_pack_focuses_current_open_statuses(self):
        config = MothersDayFollowupConfig(
            source_spreadsheet_id="source-123",
            source_workbook_title="地區會議資料V7.0 beta",
            tab_name="母親節追蹤",
            output_dir=Path("out"),
            report_date="2026-05-16",
            region="N1",
            focus_statuses=("追蹤中", "鼓勵自用體驗", "擴量中"),
            include_other_open=False,
            max_rows=0,
        )
        spreadsheet = FakeSpreadsheet(
            {
                "母親節追蹤": [
                    ["區域", "客戶名稱", "狀態", "負責人", "備註"],
                    ["N1", "甲診所", "追蹤中", "A", "活動後待確認"],
                    ["N1", "乙藥局", "擴量中", "B", "已有補貨需求"],
                    ["N2", "丙診所", "鼓勵自用體驗", "C", "跨區不列入"],
                    ["N1", "丁診所", "已完成", "D", "已結案"],
                    ["N1", "戊診所", "觀望", "E", "非預設焦點"],
                ]
            }
        )

        pack = build_followup_pack(spreadsheet=spreadsheet, config=config)

        self.assertEqual(pack["diagnostics"]["selected_rows"], 2)
        self.assertEqual([row["customer"] for row in pack["rows"]], ["乙藥局", "甲診所"])
        self.assertEqual(pack["rows"][0]["status_class"], "擴量推進")
        self.assertIn("LINE", render_markdown(pack))

    def test_include_other_open_keeps_non_closed_open_rows(self):
        config = MothersDayFollowupConfig(
            source_spreadsheet_id="source-123",
            source_workbook_title="地區會議資料V7.0 beta",
            tab_name="母親節追蹤",
            output_dir=Path("out"),
            report_date="2026-05-16",
            region="N1",
            focus_statuses=("追蹤中",),
            include_other_open=True,
            max_rows=0,
        )
        spreadsheet = FakeSpreadsheet(
            {
                "母親節追蹤": [
                    ["區域", "客戶名稱", "狀態", "備註"],
                    ["N1", "甲診所", "觀望", "仍需追蹤"],
                    ["N1", "乙診所", "已結案", "完成"],
                ]
            }
        )

        pack = build_followup_pack(spreadsheet=spreadsheet, config=config)

        self.assertEqual(pack["diagnostics"]["selected_rows"], 1)
        self.assertEqual(pack["rows"][0]["status_class"], "其他開放追蹤")

    def test_status_classification_and_line_copy_are_concise(self):
        self.assertEqual(classify_status("鼓勵自用體驗")["label"], "自用體驗轉換")

        line_text = build_line_text("甲診所", "鼓勵自用體驗")

        self.assertLessEqual(len(line_text), 120)
        self.assertIn("母親節活動後", line_text)


if __name__ == "__main__":
    unittest.main()
