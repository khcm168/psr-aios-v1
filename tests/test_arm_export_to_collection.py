import importlib
import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

import pandas as pd
import scripts.arm_export_to_collection as arm_export_module

from scripts.arm_export_to_collection import (
    ARM_COLLECTION_STATUS_CELL,
    SOURCE_COLS,
    build_collection_update_sentence,
    build_arm_webapp_payload,
    parse_excel_rows,
    parse_arm_webapp_response,
    quote_sheet_name,
    validate_arm_webapp_rows,
)


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


class ArmExportToCollectionTest(unittest.TestCase):
    def test_import_webapp_url_prefers_specific_env_then_shared_fallback(self):
        try:
            with mock.patch("dotenv.load_dotenv", return_value=True):
                with mock.patch.dict(
                    os.environ,
                    {
                        "ARM_IMPORT_WEBAPP_URL": "https://import.example/exec",
                        "ARM_WEBAPP_URL": "https://shared.example/exec",
                    },
                    clear=False,
                ):
                    importlib.reload(arm_export_module)
                    self.assertEqual(
                        arm_export_module.ARM_IMPORT_WEBAPP_URL,
                        "https://import.example/exec",
                    )

                with mock.patch.dict(
                    os.environ,
                    {
                        "ARM_IMPORT_WEBAPP_URL": "",
                        "ARM_WEBAPP_URL": "https://shared.example/exec",
                    },
                    clear=False,
                ):
                    importlib.reload(arm_export_module)
                    self.assertEqual(
                        arm_export_module.ARM_IMPORT_WEBAPP_URL,
                        "https://shared.example/exec",
                    )
        finally:
            os.environ.pop("ARM_IMPORT_WEBAPP_URL", None)
            os.environ.pop("ARM_WEBAPP_URL", None)
            importlib.reload(arm_export_module)

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

    def test_collection_status_cell_defaults_to_b1(self):
        self.assertEqual(ARM_COLLECTION_STATUS_CELL, "B1")

    def test_quote_sheet_name_escapes_apostrophes_for_sheets_range(self):
        self.assertEqual(quote_sheet_name("Collection"), "'Collection'")
        self.assertEqual(quote_sheet_name("Bob's Collection"), "'Bob''s Collection'")

    def test_arm_webapp_request_fixture_matches_local_contract(self):
        payload = json.loads((FIXTURE_DIR / "arm_webapp_request.json").read_text(encoding="utf-8"))

        self.assertEqual(
            build_arm_webapp_payload(payload["rows"], token=payload["token"]),
            payload,
        )

    def test_arm_webapp_row_validation_rejects_shape_changes(self):
        valid_row = json.loads((FIXTURE_DIR / "arm_webapp_request.json").read_text(encoding="utf-8"))["rows"][0]

        with self.assertRaisesRegex(ValueError, "must have 7 cells"):
            validate_arm_webapp_rows([valid_row[:-1]])

        invalid_closing_number = valid_row.copy()
        invalid_closing_number[3] = "not-a-closing-number"
        with self.assertRaisesRegex(ValueError, "invalid closing_number"):
            validate_arm_webapp_rows([invalid_closing_number])

        non_string_receivable = valid_row.copy()
        non_string_receivable[5] = 1000
        with self.assertRaisesRegex(ValueError, "non-string cells"):
            validate_arm_webapp_rows([non_string_receivable])

    def test_arm_webapp_response_contract(self):
        success = json.loads((FIXTURE_DIR / "arm_webapp_response_success.json").read_text(encoding="utf-8"))
        self.assertEqual(parse_arm_webapp_response(success), success)

        failure = json.loads((FIXTURE_DIR / "arm_webapp_response_error.json").read_text(encoding="utf-8"))
        with self.assertRaisesRegex(RuntimeError, "Invalid token"):
            parse_arm_webapp_response(failure)

    def test_apps_script_scaffold_is_present_for_deployed_endpoint(self):
        endpoint = Path(__file__).resolve().parents[1] / "apps_script" / "61_ARM_WebApp_Endpoint.gs"

        source = endpoint.read_text(encoding="utf-8")

        self.assertIn("function doPost(e)", source)
        self.assertIn("validateArmWebAppRows_", source)
        self.assertIn("previewAiRemitterQueue", source)
        self.assertIn("beginAiRemitterDirectRun", source)
        self.assertIn("recordAiRemitterDirectStep", source)
        self.assertIn("ARM_WEBAPP_TOKEN", source)
        self.assertIn("Collection!B:H", source)


if __name__ == "__main__":
    unittest.main()
