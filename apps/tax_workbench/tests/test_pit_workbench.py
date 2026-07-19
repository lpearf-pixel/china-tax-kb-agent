import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from apps.tax_workbench.markdown import render_markdown
from apps.tax_workbench.models import TaxFacts
from apps.tax_workbench.planner import TaxPlanningService

ROOT = Path(__file__).resolve().parents[3]


def business(**overrides):
    data = {
        "business_date": "2026-07-19", "region": "CN", "taxpayer_type": "个体工商户",
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


def labor(**overrides):
    data = {
        "business_date": "2026-07-19", "region": "CN", "taxpayer_type": "自然人",
        "vat_status": "小规模纳税人", "transaction_type": "服务", "amount": "10000",
        "amount_period": "单次", "invoice_need": "普通发票", "objective": "个人所得税",
        "description": "居民个人劳务报酬", "requested_tax_types": ["个人所得税"],
        "pit_income_category": "劳务报酬", "pit_resident_status": "居民个人",
        "pit_taxpayer_role": "独立劳务个人", "pit_labor_gross_income": "10000",
        "pit_labor_withheld_tax": "0", "pit_labor_payer_has_withholding_obligation": True,
    }
    data.update(overrides)
    return TaxFacts.from_dict(data)


class PitWorkbenchTests(unittest.TestCase):
    def service(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        return TaxPlanningService(ROOT, case_root=Path(temp.name))

    def test_individual_business_one_million_gets_half_reduction(self):
        result = self.service().analyze(business())
        pit = next(row for row in result.calculations if row["tax_type"] == "个人所得税")
        self.assertEqual(Decimal(pit["tax_amount"]["value"]), Decimal("142250.00"))
        self.assertIn("个人所得税", result.schemes[0].tax_breakdown)

    def test_2028_individual_business_does_not_get_expired_discount(self):
        result = self.service().analyze(business(business_date="2028-01-01"))
        pit = next(row for row in result.calculations if row["tax_type"] == "个人所得税")
        self.assertEqual(Decimal(pit["tax_amount"]["value"]), Decimal("284500.00"))
        self.assertNotIn("PIT-INDIVIDUAL-BUSINESS-HALF-2023-2027", pit["rule_ids"])

    def test_labor_withholding_is_not_final_annual_tax(self):
        facts = labor()
        result = self.service().analyze(facts)
        pit = next(row for row in result.calculations if row["tax_type"] == "个人所得税")
        self.assertEqual(Decimal(pit["tax_amount"]["value"]), Decimal("1600.00"))
        self.assertEqual(pit["status"], "conditional_determinate")
        self.assertIn("年度汇算", result.initial_conclusion)
        self.assertIn("年度汇算", render_markdown(facts, result))

    def test_vat_and_pit_have_separate_breakdown(self):
        facts = business(requested_tax_types=["增值税", "个人所得税"], amount="400000", total_sales_same_period="400000", original_levy_rate="0.03")
        result = self.service().analyze(facts)
        self.assertEqual({row["tax_type"] for row in result.calculations}, {"增值税", "个人所得税"})
        self.assertIn("增值税", result.schemes[0].tax_breakdown)
        self.assertIn("个人所得税", result.schemes[0].tax_breakdown)

    def test_nonresident_and_unconfirmed_partnership_require_review(self):
        nonresident = self.service().analyze(business(pit_resident_status="非居民个人"))
        self.assertTrue(nonresident.human_review_required)
        partner = self.service().analyze(business(
            pit_taxpayer_role="合伙企业自然人合伙人",
            pit_partnership_allocated_income_confirmed=False,
        ))
        self.assertTrue(partner.human_review_required)


if __name__ == "__main__":
    unittest.main()
