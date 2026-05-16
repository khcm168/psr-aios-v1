import tempfile
import unittest
from datetime import date
from pathlib import Path

import pandas as pd

from scripts.arm_export_to_collection import (
    SOURCE_COLS,
    build_collection_update_sentence,
    parse_excel_rows,
    quote_sheet_name,
)


class ArmExportToCollectionTest(unittest.TestCase):
    def test_parse_excel_rows_maps_shuffled_columns_to_canonical_order(self):
        shuffled_columns = [
            "本幣未收金額",
            "結帳單號",
            "客戶名稱",
            "本幣應收帳款",
            "發票號碼",
            "結帳單業務員",
            "發票日期",
        ]
        source_values = {
            "客戶名稱": "測試診所",
            "發票日期": "2026/05/14",
            "發票號碼": "AB12345678",
            "結帳單號": "6101-2605140001",
            "結帳單業務員": "108010",
            "本幣應收帳款": "1000",
            "本幣未收金額": "900",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "arm.xlsx"
            pd.DataFrame(
                [[source_values[column] for column in shuffled_columns]],
                columns=shuffled_columns,
            ).to_excel(file_path, index=False)

            rows = parse_excel_rows(file_path)

        self.assertEqual(rows, [[source_values[column] for column in SOURCE_COLS]])

    def test_build_collection_update_sentence_uses_requested_format(self):
        self.assertEqual(
            build_collection_update_sentence(35, date(2026, 5, 16)),
            "last update in 2026/05/16 with 35 rows",
        )

    def test_quote_sheet_name_escapes_apostrophes_for_sheets_range(self):
        self.assertEqual(quote_sheet_name("Collection"), "'Collection'")
        self.assertEqual(quote_sheet_name("Bob's Collection"), "'Bob''s Collection'")


if __name__ == "__main__":
    unittest.main()
