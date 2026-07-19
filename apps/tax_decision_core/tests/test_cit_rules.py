import unittest
from datetime import date
from pathlib import Path

from apps.tax_decision_core.rule_engine import RuleEngine
from apps.tax_decision_core.rule_loader import RuleLoader
from apps.tax_decision_core.v6_adapter import V6Adapter
from apps.tax_workbench.models import TaxFacts

ROOT = Path(__file__).resolve().parents[3]


def graph(**overrides):
    payload = {
        "business_date": "2026-07-19",
        "region": "CN",
        "taxpayer_type": "企业",
        "vat_status": "一般纳税人",
        "transaction_type": "服务",
        "amount": "1000000",
        "amount_period": "年度",
        "invoice_need": "专用发票",
        "objective": "企业所得税",
        "description": "企业所得税规则测试",
        "requested_tax_types": ["企业所得税"],
        "entity_form": "公司制企业",
        "cit_resident_status": "居民企业",
        "cit_accounting_profit": "1000000",
        "cit_adjustment_increase": "0",
        "cit_adjustment_decrease": "0",
        "cit_loss_carryforward": "0",
        "cit_tax_credit": "0",
        "cit_prepaid_tax": "0",
        "cit_employee_count_avg": "20",
        "cit_asset_total_avg": "10000000",
        "cit_restricted_industry": False,
    }
    payload.update(overrides)
    return V6Adapter().to_v7(TaxFacts.from_dict(payload), "case-cit-rules")[1]


class CitRuleTests(unittest.TestCase):
    def setUp(self):
        self.loader = RuleLoader(ROOT / "rules", vault=ROOT)
        self.engine = RuleEngine()

    def test_2026_resident_small_profit_rules_apply(self):
        rules = self.loader.load(date(2026, 7, 19), "CN", "企业所得税")
        evaluations = {item.rule_id: item for item in self.engine.evaluate_all(rules, graph(), date(2026, 7, 19)).evaluations}
        self.assertEqual(evaluations["CIT-RESIDENT-GENERAL-RATE-25"].value, "0.25")
        self.assertTrue(evaluations["CIT-SMALL-LOW-PROFIT-ELIGIBILITY-2023-2027"].value)
        self.assertEqual(evaluations["CIT-SMALL-LOW-PROFIT-TAXABLE-RATIO-2023-2027"].value, "0.25")
        self.assertEqual(evaluations["CIT-SMALL-LOW-PROFIT-RATE-2023-2027"].value, "0.20")

    def test_2028_does_not_load_temporary_small_profit_rules(self):
        ids = {rule.rule_id for rule in self.loader.load(date(2028, 1, 1), "CN", "企业所得税")}
        self.assertIn("CIT-RESIDENT-GENERAL-RATE-25", ids)
        self.assertNotIn("CIT-SMALL-LOW-PROFIT-RATE-2023-2027", ids)

    def test_sole_proprietorship_exclusion_and_nonresident_review(self):
        rules = self.loader.load(date(2026, 7, 19), "CN", "企业所得税")
        sole = {item.rule_id: item for item in self.engine.evaluate_all(rules, graph(entity_form="个人独资企业"), date(2026, 7, 19)).evaluations}
        self.assertTrue(sole["CIT-SOLE-PROP-PARTNERSHIP-EXCLUSION"].value)
        nonresident = {item.rule_id: item for item in self.engine.evaluate_all(rules, graph(cit_resident_status="非居民企业"), date(2026, 7, 19)).evaluations}
        self.assertEqual(nonresident["CIT-NONRESIDENT-MANUAL-REVIEW"].status.value, "manual_review_required")


if __name__ == "__main__":
    unittest.main()
