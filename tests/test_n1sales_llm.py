import json
import unittest

from scripts.N1salesLLM import (
    WRITEBACK_KEYS,
    build_fde_prompt,
    parse_json_from_text,
    validate_writeback_keys,
)


class N1SalesLlmTest(unittest.TestCase):
    def test_build_fde_prompt_is_json_only_instruction_not_mojibake(self):
        prompt = build_fde_prompt(
            {
                "customer_name": "測試診所",
                "customer_status_ai": "Collection",
                "used_products": "Major HA",
            }
        )

        self.assertIn("必須只輸出一個 JSON object", prompt)
        self.assertIn("customer_status_ai 是 Collection", prompt)
        self.assertIn('"ai_action_proposal"', prompt)
        self.assertNotIn("謅?", prompt)

    def test_parse_json_from_text_extracts_required_keys(self):
        parsed = parse_json_from_text(
            json.dumps(
                {
                    "ai_action_proposal": "安排短訪",
                    "ai_recommended_product": "Major HA",
                    "ai_product_reason": "曾使用相關產品",
                    "ai_proposed_line": "您好，想確認近期需求。",
                    "ai_visit_angle": "先確認需求，再約下一步。",
                },
                ensure_ascii=False,
            )
        )

        self.assertEqual(parsed["ai_action_proposal"], "安排短訪")
        self.assertEqual(set(parsed), {
            "ai_action_proposal",
            "ai_recommended_product",
            "ai_product_reason",
            "ai_proposed_line",
            "ai_visit_angle",
        })

    def test_validate_writeback_keys_fails_if_intended_columns_are_missing(self):
        with self.assertRaises(ValueError) as ctx:
            validate_writeback_keys({WRITEBACK_KEYS[0]: 1})

        self.assertIn("Missing writeback internal_key values", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
