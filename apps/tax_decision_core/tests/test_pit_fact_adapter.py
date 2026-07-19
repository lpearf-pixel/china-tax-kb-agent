import unittest
from decimal import Decimal

from apps.tax_decision_core.v6_adapter import V6Adapter
from apps.tax_workbench.models import TaxFacts


class PitFactAdapterTests(unittest.TestCase):
    def test_personal_income_tax_fields_are_mapped(self):
        facts = TaxFacts.from_dict({
            "business_date": "2026-07-19", "region": "CN", "taxpayer_type": "自然人",
            "vat_status": "小规模纳税人", "transaction_type": "服务", "amount": "1000000",
            "amount_period": "年度", "invoice_need": "普通发票", "objective": "个人所得税",
            "description": "个体工商户经营所得", "requested_tax_types": ["个人所得税"],
            "pit_income_category": "经营所得", "pit_resident_status": "居民个人",
            "pit_taxpayer_role": "个体工商户业主", "pit_business_taxable_income": "1000000",
            "pit_business_other_tax_reduction": "0", "pit_business_prepaid_tax": "0",
            "pit_multiple_business_sources": False,
        })
        self.assertEqual(facts.pit_business_taxable_income, Decimal("1000000"))
        _, graph = V6Adapter().to_v7(facts, "case-pit-adapter")
        self.assertEqual(graph.facts["pit.income_category"].current.value, "经营所得")
        self.assertEqual(graph.facts["pit.business_taxable_income"].current.value, Decimal("1000000"))
        self.assertEqual(graph.facts["case.requested_tax_types"].current.value, ["个人所得税"])

    def test_pit_requires_income_category_residency_and_role(self):
        facts = TaxFacts.from_dict({
            "business_date": "2026-07-19", "region": "CN", "taxpayer_type": "自然人",
            "vat_status": "小规模纳税人", "transaction_type": "服务", "amount": "10000",
            "amount_period": "单次", "invoice_need": "普通发票", "objective": "个人所得税",
            "description": "劳务收入", "requested_tax_types": ["个人所得税"],
        })
        errors = facts.validate()
        self.assertTrue(any("pit_income_category" in item for item in errors))
        self.assertTrue(any("pit_resident_status" in item for item in errors))
        self.assertTrue(any("pit_taxpayer_role" in item for item in errors))


if __name__ == "__main__":
    unittest.main()
