import tempfile
import time
import unittest
from datetime import date
from email.message import EmailMessage
from pathlib import Path

from scripts.collection_ai_remmiter import (
    build_collection_u_status,
    build_payment_info_export_message,
    build_single_step_post_result,
    choose_button_three_left,
    encode_gmail_raw_message,
    has_partial_downloads,
    latest_completed_download,
    mark_step_collection_u_status,
)


class CollectionAiRemmiterExportTest(unittest.TestCase):
    def test_choose_button_three_left_of_search(self):
        buttons = [object() for _ in range(6)]

        self.assertIs(choose_button_three_left(buttons, buttons[4]), buttons[1])

    def test_choose_button_three_left_requires_enough_left_buttons(self):
        buttons = [object() for _ in range(3)]

        with self.assertRaisesRegex(RuntimeError, "three positions left"):
            choose_button_three_left(buttons, buttons[2])

    def test_latest_completed_download_prefers_newest_excel_and_ignores_partial(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            download_dir = Path(temp_dir)
            older = download_dir / "older.xls"
            newer = download_dir / "newer.xlsx"
            partial = download_dir / "newest.crdownload"

            older.write_text("older", encoding="utf-8")
            time.sleep(0.01)
            newer.write_text("newer", encoding="utf-8")
            time.sleep(0.01)
            partial.write_text("partial", encoding="utf-8")

            self.assertEqual(latest_completed_download(download_dir), newer)
            self.assertTrue(has_partial_downloads(download_dir))

    def test_payment_info_export_message_attaches_download(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "payment-info.xlsx"
            file_path.write_bytes(b"excel bytes")

            message = build_payment_info_export_message(file_path, "khcm168@gmail.com")

        self.assertEqual(message["To"], "khcm168@gmail.com")
        self.assertIn("ARM", message["Subject"])
        attachments = list(message.iter_attachments())
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0].get_filename(), "payment-info.xlsx")
        self.assertEqual(attachments[0].get_payload(decode=True), b"excel bytes")

    def test_encode_gmail_raw_message_is_urlsafe_base64_text(self):
        message = EmailMessage()
        message["To"] = "khcm168@gmail.com"
        message["Subject"] = "draft"
        message.set_content("hello")

        encoded = encode_gmail_raw_message(message)

        self.assertIsInstance(encoded, str)
        self.assertNotIn("+", encoded)
        self.assertNotIn("/", encoded)

    def test_collection_u_status_uses_mmdd_post_office_wording(self):
        self.assertEqual(build_collection_u_status(date(2026, 5, 29)), "05/29開始郵局匯款作業")

    def test_mark_step_collection_u_status_adds_backend_friendly_fields(self):
        result = {"ok": True}

        mark_step_collection_u_status(result, date(2026, 5, 29))

        self.assertEqual(result["message"], "05/29開始郵局匯款作業")
        self.assertEqual(result["collectionUText"], "05/29開始郵局匯款作業")
        self.assertEqual(result["statusText"], "05/29開始郵局匯款作業")
        self.assertEqual(result["collectionUValue"], "05/29開始郵局匯款作業")

    def test_single_step_post_result_targets_one_collection_row(self):
        item = {"groupType": "cashSolo", "invoiceNo": "AB12345678"}
        step_result = {
            "stepType": "cash",
            "rowNumber": 17,
            "closingNo": "6101-2605290001",
            "ok": True,
            "message": "05/29開始郵局匯款作業",
            "collectionUText": "05/29開始郵局匯款作業",
            "statusText": "05/29開始郵局匯款作業",
            "collectionUValue": "05/29開始郵局匯款作業",
        }

        post_result = build_single_step_post_result(item, step_result)

        self.assertEqual(post_result["rowNumbers"], [17])
        self.assertEqual(post_result["closingNumbers"], ["6101-2605290001"])
        self.assertEqual(post_result["steps"], [step_result])
        self.assertEqual(post_result["collectionUText"], "05/29開始郵局匯款作業")


if __name__ == "__main__":
    unittest.main()
