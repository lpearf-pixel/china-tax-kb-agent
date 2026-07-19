import unittest

from apps.tax_decision_core.pit_issues import PitIssueEngine
from apps.tax_decision_core.v6_adapter import V6Adapter
from apps.tax_workbench.models import TaxFacts


def facts(**overrides):
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
    return TaxFacts.from_dict(data)


class PitIssueTests(unittest.TestCase):
    def identify(self, input_facts):
        case, graph = V6Adapter().to_v7(input_facts, "case-pit-issues")
        return PitIssueEngine().identify(case, graph)

    def test_business_income_creates_rate_and_discount_issues(self):
        ids = {item.issue_id for item in self.identify(facts())}
        self.assertIn("pit-business-taxable-income", ids)
        self.assertIn("pit-individual-business-half-reduction", ids)

    def test_labor_remuneration_creates_withholding_and_settlement_route(self):
        ids = {item.issue_id for item in self.identify(facts(
            pit_income_category="劳务报酬", pit_taxpayer_role="独立劳务个人",
            pit_labor_gross_income="10000", amount_period="单次",
        ))}
        self.assertIn("pit-labor-withholding", ids)
        self.assertIn("pit-comprehensive-settlement-route", ids)

    def test_nonresident_is_high_risk(self):
        review = next(item for item in self.identify(facts(pit_resident_status="非居民个人")) if item.issue_id == "pit-special-review")
        self.assertEqual(review.status, "manual_review_required")


if __name__ == "__main__":
    unittest.main()
