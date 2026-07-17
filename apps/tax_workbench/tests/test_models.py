import unittest
from decimal import Decimal

from apps.tax_workbench.models import TaxFacts, PlanningResult


class TaxFactsTests(unittest.TestCase):
    def base(self):
        return {
            "business_date": "2026-07-17",
            "region": "CN-XJ",
            "taxpayer_type": "企业",
            "vat_status": "小规模纳税人",
            "transaction_type": "服务",
            "amount": "240000",
            "amount_period": "季度",
            "invoice_need": "普通发票",
            "objective": "合规降负",
            "description": "提供咨询服务",
        }

    def test_from_dict_normalizes_amount_and_boolean_flags(self):
        data = self.base() | {"amount_tax_inclusive": "true", "related_party": "false"}
        facts = TaxFacts.from_dict(data)
        self.assertEqual(facts.amount, Decimal("240000"))
        self.assertTrue(facts.amount_tax_inclusive)
        self.assertFalse(facts.related_party)

    def test_validate_reports_missing_required_fields_and_bad_date(self):
        facts = TaxFacts.from_dict({"business_date": "2026/07/17", "region": "CN-XJ"})
        errors = facts.validate()
        self.assertTrue(any("business_date" in item for item in errors))
        self.assertTrue(any("taxpayer_type" in item for item in errors))
        self.assertTrue(any("amount" in item for item in errors))

    def test_hainan_import_missing_facts_are_review_inputs_not_validation_errors(self):
        data = self.base() | {
            "region": "CN-HI",
            "transaction_type": "进口货物",
            "hainan_special_scene": True,
            "hs_code": "",
            "qualified_entity": None,
        }
        facts = TaxFacts.from_dict(data)
        self.assertEqual(facts.validate(), [])
        missing = facts.missing_facts()
        self.assertIn("商品 HS 编码", missing)
        self.assertIn("海南自贸港享惠主体资格", missing)

    def test_result_serializes_nested_models(self):
        result = PlanningResult(initial_conclusion="初步", kb_version="KB-TEST", verified_at="2026-07-17")
        payload = result.to_dict()
        self.assertEqual(payload["initial_conclusion"], "初步")
        self.assertEqual(payload["schemes"], [])


if __name__ == "__main__":
    unittest.main()
