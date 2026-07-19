import unittest
from datetime import date
from pathlib import Path

from apps.tax_decision_core.rule_engine import RuleEngine
from apps.tax_decision_core.rule_loader import RuleLoader
from apps.tax_decision_core.v6_adapter import V6Adapter
from apps.tax_workbench.models import TaxFacts

ROOT = Path(__file__).resolve().parents[3]


def graph(**overrides):
    data = {
        "business_date": "2026-07-19", "region": "CN", "taxpayer_type": "自然人",
        "vat_status": "小规模纳税人", "transaction_type": "服务", "amount": "1000000",
        "amount_period": "年度", "invoice_need": "普通发票", "objective": "个人所得税",
        "description": "个体工商户经营所得", "requested_tax_types": ["个人所得税"],
        "pit_income_category": "经营所得", "pit_resident_status": "居民个人",
        "pit_taxpayer_role": "个体工商户业主", "pit_business_taxable_income": "1000000",
        "pit_business_other_tax_reduction": "0", "pit_business_prepaid_tax": "0",
        "pit_multiple_business_sources": False,
    }
    data.update(overrides)
    return V6Adapter().to_v7(TaxFacts.from_dict(data), "case-pit-rules")[1]


class PitRuleTests(unittest.TestCase):
    def setUp(self):
        self.loader = RuleLoader(ROOT / "rules", vault=ROOT)
        self.engine = RuleEngine()

    def evaluations(self, date_value, input_graph):
        rules = self.loader.load(date_value, "CN", "个人所得税")
        return {item.rule_id: item for item in self.engine.evaluate_all(rules, input_graph, date_value).evaluations}

    def test_2026_business_income_and_individual_business_discount_apply(self):
        rows = self.evaluations(date(2026, 7, 19), graph())
        self.assertTrue(rows["PIT-BUSINESS-INCOME-RATE-TABLE"].value)
        self.assertTrue(rows["PIT-INDIVIDUAL-BUSINESS-HALF-2023-2027"].value)

    def test_2028_does_not_load_temporary_discount(self):
        ids = {rule.rule_id for rule in self.loader.load(date(2028, 1, 1), "CN", "个人所得税")}
        self.assertIn("PIT-BUSINESS-INCOME-RATE-TABLE", ids)
        self.assertNotIn("PIT-INDIVIDUAL-BUSINESS-HALF-2023-2027", ids)

    def test_labor_and_nonresident_routes(self):
        labor = self.evaluations(date(2026, 7, 19), graph(
            pit_income_category="劳务报酬", pit_taxpayer_role="独立劳务个人",
            pit_labor_gross_income="10000", amount_period="单次",
        ))
        self.assertTrue(labor["PIT-LABOR-REMUNERATION-RESIDENT-WITHHOLDING"].value)
        nonresident = self.evaluations(date(2026, 7, 19), graph(pit_resident_status="非居民个人"))
        self.assertEqual(nonresident["PIT-NONRESIDENT-MANUAL-REVIEW"].status.value, "manual_review_required")


if __name__ == "__main__":
    unittest.main()
