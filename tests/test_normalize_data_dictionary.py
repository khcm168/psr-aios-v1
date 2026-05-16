import unittest

from scripts.normalize_data_dictionary import find_dictionary_table


class NormalizeDataDictionaryTest(unittest.TestCase):
    def test_find_dictionary_table_detects_moved_table_block(self):
        values = [
            ["notes", "", "", ""],
            ["", "", "sheet", "中文欄名", "internal_key", "type", "role", "note", "write_policy"],
            ["", "", "List", "客戶名稱", "customer_name", "text", "manual", "", ""],
        ]

        header_row, start_col, sliced = find_dictionary_table(values)

        self.assertEqual(header_row, 2)
        self.assertEqual(start_col, 3)
        self.assertEqual(sliced[0][:3], ["sheet", "中文欄名", "internal_key"])
        self.assertEqual(sliced[1][2], "customer_name")


if __name__ == "__main__":
    unittest.main()
