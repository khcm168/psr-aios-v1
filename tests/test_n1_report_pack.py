import unittest
from pathlib import Path

from app.n1_report_pack import (
    ReportPackConfig,
    build_report_pack,
    render_markdown,
    section_from_values,
    write_report_pack,
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


class N1ReportPackTest(unittest.TestCase):
    def test_section_from_values_uses_first_table_like_row_as_header(self):
        section = section_from_values(
            "今日拜訪",
            [
                ["", "", ""],
                ["客戶", "進度", "下一步"],
                ["A", "已拜訪", "追蹤報價"],
                ["", "", ""],
            ],
            max_rows=5,
        )

        self.assertEqual(section["headers"], ["客戶", "進度", "下一步"])
        self.assertEqual(section["rows"], [{"客戶": "A", "進度": "已拜訪", "下一步": "追蹤報價"}])

    def test_build_report_pack_collects_configured_sections(self):
        config = ReportPackConfig(
            source_spreadsheet_id="source-123",
            source_workbook_title="地區會議資料V7.0 beta",
            weekly_report_spreadsheet_id="weekly-123",
            operations_report_spreadsheet_id="ops-123",
            report_date="2026-04-27",
            output_dir=Path("out"),
            tabs=("Action Plan 進度", "反映事項"),
            max_rows_per_section=3,
        )
        spreadsheet = FakeSpreadsheet(
            {
                "Action Plan 進度": [["項目", "狀態"], ["N1 demo", "進行中"]],
                "反映事項": [["事項", "處理"], ["缺料", "已回報"]],
            }
        )

        pack = build_report_pack(spreadsheet=spreadsheet, config=config)
        markdown = render_markdown(pack)

        self.assertEqual(pack["reports"][0]["title"], "N1 週報 2026-04-27")
        self.assertIn("## Action Plan 進度", markdown)
        self.assertIn("| N1 demo | 進行中 |", markdown)

    def test_write_report_pack_creates_markdown_and_json(self):
        pack = {
            "source": {
                "spreadsheet_id": "source-123",
                "expected_workbook_title": "地區會議資料V7.0 beta",
                "actual_workbook_title": "地區會議資料V7.0 beta",
                "title_matches_expected": True,
            },
            "reports": [
                {"title": "N1 週報 2026-04-27", "spreadsheet_id": ""},
                {"title": "N1 地區業績營運報告 2026-04-27", "spreadsheet_id": ""},
            ],
            "sections": [],
        }
        output_dir = Path("data")
        markdown_path = output_dir / "n1_report_pack_2026-04-27.md"
        json_path = output_dir / "n1_report_pack_2026-04-27.json"
        for path in (markdown_path, json_path):
            path.unlink(missing_ok=True)

        try:
            markdown_path, json_path = write_report_pack(
                pack,
                output_dir,
                "2026-04-27",
            )
            self.assertTrue(markdown_path.exists())
            self.assertTrue(json_path.exists())
        finally:
            for path in (markdown_path, json_path):
                path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
