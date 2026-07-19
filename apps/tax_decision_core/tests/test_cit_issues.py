import unittest

from apps.tax_decision_core.cit_issues import CitIssueEngine
from apps.tax_decision_core.v6_adapter import V6Adapter
from apps.tax_workbench.models import TaxFacts


def facts(**overrides):
    payload = {
        "business_date": "2026-07-19",
        "region": "CN",
        "taxpayer_type": "企业",
        "vat_status": "一般纳税人",
        "transaction_type": "服务",
        "amount": "1000000",
        "amount_period": "年度",
        "invoice_need": "专用发票",
        "objective": "企业所得税测算",
        "description": "年度企业所得税分析",
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
    return TaxFacts.from_dict(payload)


class CitIssueEngineTests(unittest.TestCase):
    def identify(self, input_facts):
        case, graph = V6Adapter().to_v7(input_facts, "case-cit-issues")
        return CitIssueEngine().identify(case, graph)

    def test_resident_company_has_taxable_income_and_small_profit_issues(self):
        issues = self.identify(facts())
        ids = {item.issue_id for item in issues}
        self.assertIn("cit-taxpayer-scope", ids)
        self.assertIn("cit-taxable-income", ids)
        self.assertIn("cit-small-low-profit", ids)

    def test_sole_proprietorship_is_marked_not_applicable(self):
        issues = self.identify(facts(entity_form="个人独资企业"))
        scope = next(item for item in issues if item.issue_id == "cit-taxpayer-scope")
        self.assertEqual(scope.status, "not_applicable")

    def test_nonresident_creates_high_risk_manual_review_issue(self):
        issues = self.identify(facts(cit_resident_status="非居民企业"))
        review = next(item for item in issues if item.issue_id == "cit-special-review")
        self.assertEqual(review.risk_level, "high")
        self.assertEqual(review.status, "manual_review_required")


if __name__ == "__main__":
    unittest.main()
